#!/usr/bin/env python3
"""Independent path-conditioned PointNav runner. No API calls in sample/smoke."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time
import numpy as np

from core import RoutePreview, depth_facts, recent_motion_summary
from depth_language import DEPTH_FORMATS, SEMANTIC_VERSION, DISTANCE_BANDS, depth_format
from clearance import validate_reference_path
from environment import ACTIONS, Environment, direct_navmesh_connection, load_pathfinder, sample_tasks, shortest
from jev import (ENDPOINT, DEPTH_INPUT_MODES, DECISION_MODELS, DecisionsClient,
                 ServiceFailure, depth_input_mode, make_request, prompt_version, evaluation_identity, encode_request, create_decision_client)
from rgb_input import RGB_INPUT_MODES, VERSION as RGB_INPUT_VERSION, rgb_input_mode, validate_rgb_input, save_model_image
from replay import save_frame, save_map, write_replay

ROOT = Path(__file__).resolve().parent


def load_config(path):
    cfg = json.loads(Path(path).read_text())
    cfg["depth_input"] = depth_input_mode(cfg)
    cfg["depth_format"] = depth_format(cfg)
    # Missing setting preserves the motion policy of old saved configurations.
    cfg.setdefault("allow_sliding",False)
    if not isinstance(cfg["allow_sliding"],bool):
        raise ValueError("allow_sliding must be a JSON boolean")
    for key in ["move_m","turn_deg","pitch_deg","preview_m","sample_spacing_m","target_lookahead_m","success_m","max_steps","history_steps"]:
        if not isinstance(cfg[key],(int,float)) or not math.isfinite(cfg[key]) or cfg[key] <= 0:
            raise ValueError(f"{key} must be positive")
    if not 0 < cfg["near_m"] < cfg["far_m"] or not 0 < cfg["hfov_deg"] < 180:
        raise ValueError("invalid camera range/FOV")
    if cfg["target_lookahead_m"] > cfg["preview_m"]:
        raise ValueError("target lookahead must fit in preview")
    return cfg


def asset_manifest(cfg):
    result = {}
    for name in ["shuyuan.navmesh","shuyuan.mesh.ply","shuyuan.gs.ply"]:
        path = Path(cfg["scene_dir"])/name
        stat = path.stat()
        result[name] = {"path": str(path.resolve()), "bytes": stat.st_size,"mtime_ns": stat.st_mtime_ns}
        if name.endswith("navmesh"):
            result[name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def stop_status(action, distance, tolerance):
    if action != "stop":
        return None
    return "success" if distance is not None and distance <= tolerance else "early_stop"


def percentiles(values):
    return {"p50_s":float(np.percentile(values,50)),"p95_s":float(np.percentile(values,95))} if values else None


def run_episode(args, cfg):
    validate_rgb_input(cfg, args.rgb)
    rgb_mode = rgb_input_mode(cfg)
    use_rgb = rgb_mode != 'none'
    depth_mode = depth_input_mode(cfg)
    representation = depth_format(cfg) if depth_mode == "mesh" else "none"
    if representation == "semantic" and cfg["sectors"] != 9:
        raise ValueError("semantic depth requires nine sectors")
    # Fail before renderer initialization if the user has not configured the API.
    identity = evaluation_identity(cfg,live=args.command == "run")
    client = create_decision_client(cfg) if args.command == "run" else None
    provider = identity["provider"]
    dataset = json.loads(Path(args.tasks).read_text())
    task = next((t for t in dataset["tasks"] if t["id"] == args.episode),None)
    if task is None:
        raise ValueError(f"unknown episode {args.episode}")
    manifest = asset_manifest(cfg)
    old_nav = dataset.get("assets",{}).get("shuyuan.navmesh",{}).get("sha256")
    if old_nav and old_nav != manifest["shuyuan.navmesh"]["sha256"]:
        raise ValueError("NavMesh changed since task generation")
    pf = load_pathfinder(cfg)
    if not pf.is_navigable(task["start"]) or not pf.is_navigable(task["goal"]):
        raise ValueError("task endpoints are not navigable")
    check = shortest(pf,task["start"],task["goal"])
    if check is None or not math.isclose(check[0],task["geodesic_m"],abs_tol=.02):
        raise ValueError("task path is unreachable or inconsistent")
    if task.get("reference_path_kind") == "clearance_weighted":
        validate_reference_path(pf, task["path"], task["start"], task["goal"])
    route = RoutePreview(task["path"], reconnect=lambda start, end: direct_navmesh_connection(pf, start, end))
    if not np.allclose(route.points[0],task["start"],atol=.03) or not np.allclose(route.points[-1],task["goal"],atol=.03):
        raise ValueError("reference path endpoints differ from task")
    output = Path(args.out)
    output.mkdir(parents=True,exist_ok=False)
    (output/"frames").mkdir()
    scripts = args.actions.split(",") if args.command == "smoke" else []
    records, history, latencies, cycles = [], [], [], []
    collisions = invalid = steps = 0
    travel, reached, final_distance = 0., False, check[0]
    status, env = "action_budget", None
    metadata = {**identity,"rgb_mode":args.rgb,"task":task,"config":cfg,"assets":manifest,
        "available_actions":list(ACTIONS),"prompt_version":prompt_version(cfg),
        "depth_input":depth_mode,"depth_provided_to_model":depth_mode == "mesh",
        "depth_format":representation,
        "semantic_depth":{"version":SEMANTIC_VERSION,"upper_bounds_inclusive_m":dict((label,limit) for limit,label in DISTANCE_BANDS),
                          "diagnostics":"depth_numeric_debug is local only, not in request"} if representation == "semantic" else None,
        "rgb_input":rgb_mode, "rgb_provided_to_model":use_rgb and client is not None,
        "model_input_image_version":RGB_INPUT_VERSION if use_rgb else None,
        "request_representation":"readable_text_state_plus_image_manifest" if use_rgb else "wire_json",
        "api_provider":getattr(client,"api_provider","openrouter") if client else None,
        "api_endpoint":getattr(client,"endpoint",ENDPOINT) if client else None,
        **({"onejev_service_health":client.health,"onejev_deployment":client.deployment} if client and provider == "onejev_local" else {}),
        **({"omnijev_service_health":client.health,"omnijev_deployment":client.deployment} if client and provider == "omnijev_local" else {}),
        "created_unix":time.time(),"depth_source":"shuyuan.mesh.ply", "allow_sliding":cfg["allow_sliding"],
        "collision_semantics":"Habitat Agent NavMesh movement-filter collision, not Bullet contact",
        "route_policy":"fixed supplied reference polyline; checked reassociation to nearby later segments; no replanning or controller substitution",
        "reference_path_kind":task.get("reference_path_kind","navmesh_shortest"),
        "reference_path_length_m":route.total,
        "reference_planner":task.get("reference_planner"),
        "route_policy_version":RoutePreview.VERSION,
        "reassociation":{"max_distance_m":RoutePreview.MAX_REFERENCE_DISTANCE_M,
                         "connector_sample_m":.05,"connector_endpoint_tolerance_m":1e-4},
        "memory":"recent own local action outcomes and their motion summary only; no persistent obstacle map",
        "map":save_map(pf,task["start"][1],output)}
    (output/"metadata.json").write_text(json.dumps(metadata,indent=2,allow_nan=False))
    print("OUTPUT",output,flush=True)
    log = (output/"steps.jsonl").open("x",buffering=1)
    began = time.perf_counter()
    try:
        env = Environment(cfg,output,args.rgb)
        env.reset(task)
        print("[init] Environment ready; starting decision loop.",flush=True)
        for index in range(cfg["max_steps"]):
            start_time = time.perf_counter()
            position, yaw = env.pose()
            depth,rgb = env.observe()
            images = save_frame(output,index,depth,rgb)
            state = {"task": {"kind":"reference_path_following", "stop_tolerance_m":cfg["success_m"],
                        "step":index+1,"steps_left":cfg["max_steps"]-index},
                "reference":route.state(position,yaw,cfg),
                "robot": {"radius_m":cfg["agent_radius_m"],"height_m":cfg["agent_height_m"],
                    "camera_pitch_deg":env.pitch,"pitch_limits_deg":[cfg["pitch_min_deg"],cfg["pitch_max_deg"]],
                    "previous_collided":history[-1]["collided"] if history else False},
                **({"depth":depth_facts(depth,env.pitch,cfg)} if depth_mode == "mesh" else {}),
                "recent_actions":history[-cfg["history_steps"]:],
                "recent_motion":recent_motion_summary(history,cfg["history_steps"],cfg["move_m"])}
            image_input, image_bytes = None, None
            if use_rgb:
                image_input, image_bytes = save_model_image(output,index,rgb,
                    state['reference']['current_target'],env.pitch,cfg,
                    target_height_m=float(route.current_target_point[1]-position[1]))
                images['model_rgb'] = image_input['path']
                state['visual'] = {'source': 'current_'+args.rgb+'_rgb',
                                   'marker': image_input['marker']}
            request = make_request(state,cfg)
            record = {"step":index,"frame_kind":"before_action","images":images,
                "pose":{"position":position.tolist(),"yaw_rad":yaw,"pitch_deg":env.pitch},"request":request}
            if use_rgb:
                record.update(image_input=image_input,
                    wire_request_sha256=hashlib.sha256(encode_request(request,image_bytes)).hexdigest(),
                    wire_state_encoding=getattr(client,'wire_state_encoding',
                        'object_plus_inline_image' if cfg['model']==DECISION_MODELS['omnijev'] else
                        'object_plus_media_image_placeholder' if cfg['model']==DECISION_MODELS['onejev'] else
                        'array_of_text_string_and_image_url'))
            if representation == "semantic":
                record["depth_numeric_debug"] = state["depth"]
            try:
                if client:
                    print(f"[{provider}] Requesting action {index+1}/{cfg['max_steps']} via {metadata['api_provider']} ({cfg['model']})...",flush=True)
                    decision = client.decide(request,image_bytes=image_bytes) if use_rgb else client.decide(request)
                else:
                    if index >= len(scripts):
                        status = "script_complete"
                        record.update(decision=None,outcome=None,metrics={})
                        records.append(record);log.write(json.dumps(record,allow_nan=False)+"\n")
                        break
                    decision = {"provider":provider,"choice":scripts[index],"latency_s":0.,"response":None}
            except ServiceFailure as exc:
                status = "service_failure"
                record.update(decision={"error":str(exc),"attempts":exc.attempts,"latency_s":exc.latency_s},outcome=None,metrics={})
                records.append(record);log.write(json.dumps(record,allow_nan=False)+"\n")
                break
            action = decision["choice"]
            outcome = env.act(action)
            after,_ = env.pose()
            path = shortest(pf,after,task["goal"])
            final_distance = path[0] if path else None
            reached |= final_distance is not None and final_distance <= cfg["success_m"]
            steps += 1
            collisions += int(outcome["collided"])
            invalid += int(not outcome["valid"])
            travel += float(np.linalg.norm(after-position))
            history.append(outcome)
            history = history[-cfg["history_steps"]:]
            if client:
                latencies.append(decision["latency_s"])
            cycles.append(time.perf_counter()-start_time)
            record.update(decision=decision,outcome=outcome,
                after_position=after.tolist(),metrics={"distance_to_goal_geodesic_m":final_distance,
                    "path_length_m":travel,"cycle_s":cycles[-1]})
            records.append(record);log.write(json.dumps(record,allow_nan=False)+"\n")
            print(json.dumps({"step":steps,"action":action,"collided":outcome["collided"],"valid":outcome["valid"],"distance_m":final_distance}),flush=True)
            stopped = stop_status(action,final_distance,cfg["success_m"])
            if stopped:
                status = stopped
                break
        # Preserve final post-action observation as well, without another API call.
        if records and records[-1].get("outcome") is not None:
            depth,rgb = env.observe()
            position,yaw = env.pose()
            terminal = {"step":steps,"frame_kind":"after_final_action", "images":save_frame(output,len(records),depth,rgb),
                "pose":{"position":position.tolist(),"yaw_rad":yaw,"pitch_deg":env.pitch},
                "request":None,"decision":None,"outcome":None,"metrics":{"distance_to_goal_geodesic_m":final_distance}}
            records.append(terminal);log.write(json.dumps(terminal,allow_nan=False)+"\n")
    except KeyboardInterrupt:
        status = "interrupted"
        metadata["runtime_error"] = "KeyboardInterrupt"
        print("[run] Interrupted; closing renderers and saving the run record.",flush=True)
    except BaseException as exc:
        status = "runtime_failure"
        metadata["runtime_error"] = type(exc).__name__+": "+str(exc)
        raise
    finally:
        log.close()
        if env is not None:
            env.close()
        summary = {**identity,"status":status,
            "response_models":sorted({r["decision"]["response"]["model"] for r in records
                if ((r.get("decision") or {}).get("response") or {}).get("model")}),
            "depth_input":depth_mode,"depth_provided_to_model":depth_mode == "mesh","depth_format":representation,
            "rgb_input":rgb_mode,"rgb_provided_to_model":use_rgb and client is not None,
            "success":status=="success", "collision_free_success":status=="success" and collisions==0,
            "steps":steps,"collisions":collisions,"invalid_actions":invalid,
            "path_length_m":travel,"initial_geodesic_m":check[0],"final_geodesic_m":final_distance,
            "ever_within_goal_tolerance":reached,"reached_but_not_successful_stop":reached and status!="success",
            "spl":check[0]/max(check[0],travel) if status=="success" else 0.,
            "model_request_latency":percentiles(latencies),
            "jev_request_latency":percentiles(latencies) if identity["is_jev_evaluation"] else None,
            "cycle_including_render_and_logging":percentiles(cycles),
            "elapsed_s":time.perf_counter()-began}
        (output/"metadata.json").write_text(json.dumps(metadata,indent=2,allow_nan=False))
        (output/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False))
        write_replay(output,metadata,records,summary)
        print("SUMMARY",json.dumps(summary,allow_nan=False),flush=True)
    return 130 if status == "interrupted" else 2 if status in ("service_failure","runtime_failure") else 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config",default=str(ROOT/"config.json"))
    commands = p.add_subparsers(dest="command",required=True)
    sample = commands.add_parser("sample",help="sample reachable tasks without a renderer or API")
    sample.add_argument("--count",type=int,default=10)
    sample.add_argument("--seed",type=int,default=20260928)
    sample.add_argument("--out",required=True)
    for name in ["smoke","run"]:
        sub = commands.add_parser(name)
        sub.add_argument("--tasks",required=True)
        sub.add_argument("--episode",default="episode-000")
        sub.add_argument("--out",required=True)
        sub.add_argument("--rgb",choices=["gs","mesh","none"],default="gs")
        sub.add_argument("--rgb-input",choices=RGB_INPUT_MODES,
                         help="none (default): replay RGB only; target_marked: send waypoint-marked RGB to OpenAI, local OneJev or OmniJev")
        sub.add_argument("--max-steps",type=int)
        sub.add_argument("--decision-model",choices=DECISION_MODELS,
                         help="jev/openai via OpenRouter or onejev/omnijev locally; default uses config.model")
        sub.add_argument("--onejev-url",help="local qev HTTP origin (onejev only; default localhost:8011)")
        sub.add_argument("--onejev-timeout-s",type=float,help="local request timeout, default 30 seconds")
        sub.add_argument("--omnijev-url",help="local MSO1 HTTP origin (omnijev only; default localhost:8012)")
        sub.add_argument("--omnijev-timeout-s",type=float,help="local OmniJev request timeout, default 60 seconds")
        sub.add_argument("--depth-format",choices=DEPTH_FORMATS,
                         help="numeric (default) or nine-sector semantic depth facts; depth-input none takes precedence")
        sub.add_argument("--depth-input",choices=DEPTH_INPUT_MODES,
                         help="mesh: send depth facts (default); none: omit depth facts, retain replay images")
        if name == "smoke":
            sub.add_argument("--actions",default="look_down,look_down,look_down,look_down,move_forward,turn_left,turn_right,look_up,stop")
    args = p.parse_args()
    cfg = load_config(args.config)
    if args.command == "sample":
        if args.count <= 0:
            p.error("--count must be positive")
        dataset = sample_tasks(cfg,args.count,args.seed)
        dataset["assets"] = asset_manifest(cfg)
        path = Path(args.out);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("x") as f:
            json.dump(dataset,f,indent=2,allow_nan=False)
        print("TASKS",path,"count",len(dataset["tasks"]),flush=True)
        return 0
    if args.depth_format is not None:
        cfg["depth_format"] = args.depth_format
    if args.rgb_input is not None:
        cfg["rgb_input"] = args.rgb_input
    if args.decision_model is not None:
        cfg["model"] = DECISION_MODELS[args.decision_model]
    if args.onejev_url is not None or args.onejev_timeout_s is not None:
        if cfg["model"] != DECISION_MODELS["onejev"]:
            p.error("--onejev-url/--onejev-timeout-s require --decision-model onejev")
        if args.onejev_url is not None: cfg["onejev_url"] = args.onejev_url
        if args.onejev_timeout_s is not None: cfg["onejev_timeout_s"] = args.onejev_timeout_s
    if cfg["model"] == DECISION_MODELS["onejev"] and args.command == "run" and not os.environ.get("CUDA_VISIBLE_DEVICES"):
        p.error("Set CUDA_VISIBLE_DEVICES explicitly to your allocated rendering GPU for OneJev")
    if args.omnijev_url is not None or args.omnijev_timeout_s is not None:
        if cfg['model'] != DECISION_MODELS['omnijev']:
            p.error('--omnijev-url/--omnijev-timeout-s require --decision-model omnijev')
        if args.omnijev_url is not None: cfg['omnijev_url'] = args.omnijev_url
        if args.omnijev_timeout_s is not None: cfg['omnijev_timeout_s'] = args.omnijev_timeout_s
    if cfg['model'] == DECISION_MODELS['omnijev'] and args.command == 'run' and not os.environ.get('CUDA_VISIBLE_DEVICES'):
        p.error('Set CUDA_VISIBLE_DEVICES explicitly to your allocated rendering GPU for OmniJev')
    if args.depth_input is not None:
        cfg["depth_input"] = args.depth_input
    if args.max_steps is not None:
        if args.max_steps <= 0:
            p.error("--max-steps must be positive")
        cfg["max_steps"] = args.max_steps
    return run_episode(args,cfg)


if __name__ == "__main__":
    raise SystemExit(main())
