"""OpenRouter Jev Decisions client; stdlib only, no SDK/environment changes.

Reference (checked 2026-09-28):
https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request
No automatic action substitution; unknown action names are evaluated as invalid.
"""
import json
import math
import os
import time
import urllib.error
import urllib.request


ENDPOINT = "https://openrouter.ai/api/alpha/decisions"


def make_request(state, cfg):
    step, turn, pitch = cfg["move_m"], cfg["turn_deg"], cfg["pitch_deg"]
    criteria = {
        "move_forward": f"Translate forward {step} metres without changing body heading.",
        "move_backward": f"Translate backward {step} metres without changing body heading.",
        "move_left": f"Translate left {step} metres without turning.",
        "move_right": f"Translate right {step} metres without turning.",
        "turn_left": f"Rotate body left {turn} degrees in place.",
        "turn_right": f"Rotate body right {turn} degrees in place.",
        "look_up": f"Tilt camera up {pitch} degrees; does not move the body or change goal bearing.",
        "look_down": f"Tilt camera down {pitch} degrees; does not move the body or change goal bearing.",
        "stop": "End the episode permanently. Choose only when at the final destination, not at an intermediate point."}
    instructions = (
        "Choose one next action to follow the supplied reference path to its final destination efficiently while avoiding collisions. "
        "All positions are relative to the CURRENT BODY: forward positive, left positive, bearing positive left; metres and degrees. "
        "The ordered path preview can bend behind an obstacle. Follow the current_target and the ordered path; do not cut straight to the farthest point. "
        "Use mesh-depth observations and recent own-action outcomes to choose movement, observation, or recovery. "
        "Blocked indicates observed obstacles in the move volume. Unknown is not clear; an unseen low obstacle may exist. "
        "Clear is only a sampled depth estimate, not a collision guarantee. Camera pitch is positive down. "
        "Avoid repeatedly executing an ineffective action or alternating opposite actions without progress. "
        "Temporary movement away from the target is allowed for recovery. Use camera tilts to inspect unseen nearby floor when useful. "
        "Respect pitch limits. Stop only near the FINAL goal using the stated tolerance; otherwise continue. "
        "There is no automatic recovery controller and no action safety override; your selected action is executed subject to the simulator's physical constraints.")
    return {"model": cfg["model"], "state": state,
            "questions": {"action": {"type": "choice", "instructions": instructions, "criteria": criteria}}}


class ServiceFailure(RuntimeError):
    def __init__(self, message, attempts, latency_s):
        super().__init__(message)
        self.attempts, self.latency_s = attempts, latency_s


class JevClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.key = os.environ.get("OPENROUTER_API_KEY")
        if not self.key:
            raise ValueError("OPENROUTER_API_KEY is not configured; no Jev calls made")

    def decide(self, payload):
        started, errors = time.perf_counter(), []
        for attempt in range(self.cfg["api_retries"]+1):
            try:
                req = urllib.request.Request(ENDPOINT, data=json.dumps(payload,allow_nan=False).encode(),
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
                return {"provider": "jev", "api_provider": "openrouter", "response": result, "choice": answer["choice"],
                        "latency_s": time.perf_counter()-started, "attempts": attempt+1,
                        "retry_errors": errors}
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
        raise ServiceFailure("Jev request failed: "+", ".join(errors),len(errors),time.perf_counter()-started)
