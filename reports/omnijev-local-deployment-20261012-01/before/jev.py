"""OpenRouter Decisions client for Jev/OpenAI; stdlib only, no SDK changes.

Reference (OpenRouter protocol checked 2026-10-09):
https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request
No automatic action substitution; unknown action names are evaluated as invalid.
"""
import json
import base64
import hashlib
import math
import os
import time
import urllib.error
import urllib.request
from depth_language import depth_format, semantic_depth
from rgb_input import rgb_input_mode


ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
PROMPT_VERSION = "seven_actions_reassociate_motion_v5"
NO_DEPTH_PROMPT_VERSION = PROMPT_VERSION + "_no_depth"
DEPTH_INPUT_MODES = ("mesh", "none")
DECISION_MODELS = {"jev": "typesafe/jev-1.13", "openai": "openai/gpt-6-luna-decisions", "onejev": "OmniJev/OneJev-4B"}


def evaluation_identity(cfg, live=True):
    model = cfg["model"]
    if model == DECISION_MODELS["onejev"]:
        family, label = "onejev_local", "OneJev-4B"
    elif model == DECISION_MODELS["openai"]:
        family, label = "openai_decisions", "GPT-6 Luna Decisions"
    elif isinstance(model,str) and model.lstrip("~").startswith("typesafe/jev-"):
        family, label = "jev", "Jev"
    else:
        raise ValueError("unsupported decision model; select --decision-model jev, openai or onejev")
    return {"provider":family if live else "scripted_smoke", "requested_model":model,
            "model_label":label, "is_model_evaluation":bool(live),
            "is_jev_evaluation":bool(live and family == "jev"),
            "is_openai_decisions_evaluation":bool(live and family == "openai_decisions"),
            **({"is_onejev_evaluation":bool(live)} if family == "onejev_local" else {})}


def depth_input_mode(cfg):
    mode = cfg.get("depth_input", "mesh")
    if mode not in DEPTH_INPUT_MODES:
        raise ValueError("depth_input must be 'mesh' or 'none'")
    return mode


def prompt_version(cfg):
    version = NO_DEPTH_PROMPT_VERSION if depth_input_mode(cfg) == "none" else (
        PROMPT_VERSION + "_semantic_depth_v1" if depth_format(cfg) == "semantic" else PROMPT_VERSION)
    return version + "_target_marked_rgb_v1" if rgb_input_mode(cfg) != "none" else version


def make_request(state, cfg):
    use_depth = depth_input_mode(cfg) == "mesh"
    use_rgb = rgb_input_mode(cfg) != "none"
    if not use_depth:
        # Enforce the ablation at the API boundary too; never mutate caller state.
        state = {key: value for key, value in state.items() if key != "depth"}
    use_semantic = use_depth and depth_format(cfg) == "semantic"
    if use_semantic and "depth" in state:
        state = dict(state, depth=semantic_depth(state["depth"]))
    step, turn, pitch = cfg["move_m"], cfg["turn_deg"], cfg["pitch_deg"]
    stop_rule = (
        "STOP RULE (highest priority): When reference.current_target.is_final is true and "
        "reference.final_goal.distance_m <= task.stop_tolerance_m "
        f"({cfg['success_m']:g} metres, inclusive), choose stop immediately. "
        "Being inside this tolerance is arrival; do not try to reach zero distance or align body heading or camera pitch. "
        "This rule takes priority over path following, further movement, turning, observation, and recovery. "
        "Reaching an intermediate path point is not arrival at the final destination. ")
    criteria = {
        "move_forward": f"Translate forward {step} metres without changing body heading.",
        "move_backward": f"Translate backward {step} metres without changing body heading.",
        "turn_left": f"Rotate body left {turn} degrees in place.",
        "turn_right": f"Rotate body right {turn} degrees in place.",
        "look_up": f"Tilt camera up {pitch} degrees; does not move the body or change goal bearing.",
        "look_down": f"Tilt camera down {pitch} degrees; does not move the body or change goal bearing.",
        "stop": (f"End the episode now when the current target is final and the final-goal distance is at most {cfg['success_m']:g} metres, "
                 "including the boundary. Arrival within tolerance is sufficient; no additional movement or alignment is needed. "
                 "Do not stop at an intermediate target or outside the final-goal tolerance.")}
    perception = (
        "Use mesh-depth observations and recent own-action outcomes to "
        "choose movement, observation, or recovery. Blocked indicates observed obstacles in the move volume. Unknown is not "
        "clear; an unseen low obstacle may exist. Clear is only a sampled depth estimate, not a collision guarantee. "
        if use_depth else
        "No depth or image observations are provided. Use the supplied reference path and recent own-action outcomes. "
        "Camera tilts do not reveal environmental observations in this condition. ")
    if use_rgb and not use_depth:
        perception = ("No depth observations are provided. Use the current RGB image, supplied reference path "
                      "and recent own-action outcomes. Camera tilts provide a new RGB observation. ")
    if use_semantic:
        perception += (
            "Depth is described in words. Directions are ordered from the right edge through straight ahead to the left edge "
            "of the current forward view; side edges do not describe the body's full left or right surroundings. "
            "Obstacle distance bands, nearest to farthest, are very close, close, moderately near, far, very far. "
            "These are obstacle ranges, not guaranteed free movement distances. Unknown and no_obstacle_seen do not mean far or safe. "
            "Surface range describes observed surfaces, separately from obstacles. Nearby floor not confirmed visible indicates a blind region. ")
    if use_rgb:
        perception += (
            "A current RGB image accompanies this text. The magenta virtual marker refers only to "
            "reference.current_target. A circle is its geometric projection; it does not prove visibility, "
            "free space, or a direct safe route. A border arrow explicitly means the target is outside the "
            "image or behind the camera, not a ground point at the arrow's pixel. It may be necessary to "
            "turn or look down to inspect it. Use image obstacles together with the available text and feedback. "
            "The marker is not an environmental object. It is an intermediate waypoint unless is_final is true. ")
    floor_inspection = "Use camera tilts to inspect unseen nearby floor when useful. " if use_depth or use_rgb else ""
    instructions = (
        stop_rule +
        "Choose one next action to follow the supplied reference path to its final destination efficiently while avoiding "
        "collisions. All positions are relative to the CURRENT BODY: forward positive, left positive, bearing positive left; "
        "metres and degrees. The ordered path preview can bend behind an obstacle. Follow the current_target and the ordered "
        "path; do not cut straight to the farthest point. " + perception +
        "Camera pitch is positive down. Avoid repeatedly executing an ineffective action or alternating opposite actions without "
        "progress. Temporary movement away from the target is allowed for recovery. " + floor_inspection +
        "Respect pitch limits. Stop only near the FINAL goal using the stated tolerance; otherwise "
        "continue. There is no automatic recovery controller and no action safety override; your selected action is executed "
        "subject to the simulator's physical constraints. "
        "recent_motion summarizes only recent_actions. Action success means the action executed, not that navigation advanced. "
        "If recent_motion.status is turn_oscillation, recent opposite turns have produced little net translation: "
        "avoid repeating that left-right pair and choose a different observation or recovery, such as inspecting farther "
        "in one turn direction or backing away when appropriate. A no_translation status alone can also mean useful observation. "
        "When reference.tracking.mode is reassociated, follow the updated current_target and ordered_preview.")
    return {"model": cfg["model"], "state": state,
            "questions": {"action": {"type": "choice", "instructions": instructions, "criteria": criteria}}}


class ServiceFailure(RuntimeError):
    def __init__(self, message, attempts, latency_s):
        super().__init__(message)
        self.attempts, self.latency_s = attempts, latency_s


def encode_request(payload, image_bytes=None):
    """Wire representation only; callers keep readable text states in logs."""
    if payload.get("model") == DECISION_MODELS["onejev"]:
        from onejev import encode_local_request
        return encode_local_request(payload, image_bytes)
    if image_bytes is not None:
        if payload['model'] != DECISION_MODELS['openai']:
            raise ValueError('RGB input currently requires the OpenAI decision model')
        if not isinstance(image_bytes, bytes) or not image_bytes:
            raise ValueError('current RGB image bytes are required')
        payload = dict(payload, state=[json.dumps(payload['state'], allow_nan=False),
            {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(image_bytes).decode('ascii')}}])
    return json.dumps(payload, allow_nan=False).encode()


class DecisionsClient:
    def __init__(self, cfg):
        if cfg["model"] == DECISION_MODELS["onejev"]:
            raise ValueError("OneJev requires create_decision_client and local transport")
        self.cfg = cfg
        self.identity = evaluation_identity(cfg)
        self.key = os.environ.get("OPENROUTER_API_KEY")
        if not self.key:
            raise ValueError("OPENROUTER_API_KEY is not configured; no model calls made")

    def decide(self, payload, image_bytes=None):
        if (rgb_input_mode(self.cfg) != 'none') != (image_bytes is not None):
            raise ValueError('RGB input setting and current image bytes must agree')
        body = encode_request(payload, image_bytes)
        started, errors = time.perf_counter(), []
        for attempt in range(self.cfg["api_retries"]+1):
            try:
                req = urllib.request.Request(ENDPOINT, data=body,
                    headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req,timeout=self.cfg["api_timeout_s"]) as response:
                    result = json.load(response)
                if not isinstance(result,dict) or not isinstance(result.get("answers"),dict):
                    raise ValueError("missing answers object")
                answer = result["answers"]["action"]
                if not isinstance(answer,dict) or not isinstance(answer.get("choice"),str):
                    raise ValueError("missing action choice")
                probabilities = answer["probabilities"]
                if not isinstance(probabilities,dict) or not probabilities:
                    raise ValueError("invalid probabilities")
                if any(not isinstance(v,(float,int)) or not math.isfinite(v) or not 0 <= v <= 1 for v in probabilities.values()):
                    raise ValueError("invalid probabilities")
                return {"provider": self.identity["provider"], "requested_model":self.cfg["model"],
                        "api_provider": "openrouter", "response": result, "choice": answer["choice"],
                        "latency_s": time.perf_counter()-started, "attempts": attempt+1,
                        "retry_errors": errors,
                        **({'request_body_sha256': hashlib.sha256(body).hexdigest()} if image_bytes is not None else {})}
            except urllib.error.HTTPError as exc:
                errors.append(f"HTTP {exc.code}")
                if exc.code not in (408,429,500,502,503,504,524,529):
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                errors.append(type(exc).__name__)
            except (ValueError,KeyError,TypeError) as exc:
                errors.append("invalid_response:"+type(exc).__name__)
                break
            if attempt < self.cfg["api_retries"]:
                time.sleep(min(2**attempt,4))
        # Never echo request headers, raw error bodies, or keys.
        raise ServiceFailure("OpenRouter Decisions request failed: "+", ".join(errors),len(errors),time.perf_counter()-started)


# Preserve existing imports and downstream scripts.
JevClient = DecisionsClient


def create_decision_client(cfg):
    """Keep local decisions independent of OpenRouter keys and SDKs."""
    if cfg["model"] == DECISION_MODELS["onejev"]:
        from onejev import OneJevClient
        return OneJevClient(cfg)
    return DecisionsClient(cfg)
