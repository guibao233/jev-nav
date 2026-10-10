"""Habitat-GS adapter. Mesh owns depth/motion; optional GS renderer follows its pose."""
import json
import math
from contextlib import contextmanager
from pathlib import Path
import signal
import time
import numpy as np

from core import relative


ACTIONS = ("move_forward", "move_backward", "turn_left", "turn_right", "look_up", "look_down", "stop")


@contextmanager
def defer_startup_interrupt():
    """Finish a native constructor before SIGINT can leave it half-initialized.

    Used on the CLI's main thread. The caller assigns the completed simulator
    inside this scope, so its exception handler can close it on cancellation.
    """
    pending = False
    previous = signal.getsignal(signal.SIGINT)

    def remember_interrupt(signum, frame):
        nonlocal pending
        pending = True

    signal.signal(signal.SIGINT, remember_interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)
    if pending:
        raise KeyboardInterrupt


def load_pathfinder(cfg):
    import habitat_sim as h
    pf = h.PathFinder()
    path = Path(cfg["scene_dir"]) / "shuyuan.navmesh"
    if not pf.load_nav_mesh(str(path)):
        raise RuntimeError(f"cannot load NavMesh: {path}")
    settings = pf.nav_mesh_settings
    if settings is None:
        raise RuntimeError("NavMesh has no saved agent dimensions")
    cfg["agent_radius_m"] = float(settings.agent_radius)
    cfg["agent_height_m"] = float(settings.agent_height)
    return pf


def shortest(pf, start, goal):
    import habitat_sim as h
    path = h.ShortestPath()
    path.requested_start = np.asarray(start, dtype=np.float32)
    path.requested_end = np.asarray(goal, dtype=np.float32)
    if not pf.find_path(path) or not np.isfinite(path.geodesic_distance):
        return None
    return float(path.geodesic_distance), [np.asarray(p).tolist() for p in path.points]


def sample_tasks(cfg, count, seed):
    pf = load_pathfinder(cfg)
    pf.seed(seed)
    rng = np.random.default_rng(seed)
    island = max(range(pf.num_islands), key=pf.island_area)
    buckets = {"straight": [], "corner": [], "detour": []}
    attempts = 0
    for attempts in range(1, 20001):
        start = np.asarray(pf.get_random_navigable_point(island_index=island))
        goal = np.asarray(pf.get_random_navigable_point_near(start, cfg["task_max_m"], island_index=island))
        if not np.isfinite(start).all() or not np.isfinite(goal).all():
            continue
        if not pf.is_navigable(start) or not pf.is_navigable(goal) or abs(start[1]-goal[1]) > .25:
            continue
        if min(pf.distance_to_closest_obstacle(start, .25), pf.distance_to_closest_obstacle(goal, .25)) < .10:
            continue
        path = shortest(pf, start, goal)
        if path is None or not cfg["task_min_m"] <= path[0] <= cfg["task_max_m"]:
            continue
        ratio = path[0] / max(float(np.linalg.norm(goal-start)), 1e-6)
        category = "straight" if ratio < 1.05 else ("corner" if ratio < 1.2 else "detour")
        quota = (count+2)//3
        if len(buckets[category]) < quota:
            buckets[category].append({"start": start.tolist(), "goal": goal.tolist(),
                "yaw_deg": float(rng.uniform(-180,180)), "pitch_deg": 0,
                "geodesic_m": path[0], "path": path[1], "category": category,
                "geodesic_to_euclidean_ratio": ratio})
        if sum(map(len,buckets.values())) >= 3*quota:
            break
    tasks = []
    for i in range((count+2)//3):
        for bucket in buckets.values():
            if i < len(bucket) and len(tasks) < count:
                tasks.append(dict(bucket[i], id=f"episode-{len(tasks):03d}"))
    if len(tasks) != count:
        raise RuntimeError(f"sampled only {len(tasks)}/{count} tasks after {attempts} attempts")
    return {"schema": 1, "seed": seed, "sampling_attempts": attempts,
            "category_definition": "geodesic/euclidean ratio: straight<1.05; corner<1.2; detour>=1.2 (geometric proxies, not semantic labels)",
            "scene_dir": str(Path(cfg["scene_dir"]).resolve()),
            "agent_radius_m": cfg["agent_radius_m"], "agent_height_m": cfg["agent_height_m"],
            "tasks": tasks}


class Environment:
    def __init__(self, cfg, output, rgb_mode="gs"):
        import habitat_sim as h
        self.cfg, self.h, self.pitch, self.rgb_mode = cfg, h, 0., rgb_mode
        self.mesh = self.gs = None
        self.pf = load_pathfinder(cfg)
        stage = Path(output) / "mesh.stage_config.json"
        mesh = str(Path(cfg["scene_dir"]) / "shuyuan.mesh.ply")
        stage.write_text(json.dumps({"render_asset": mesh, "collision_asset": mesh,
            "up": [0,1,0], "front": [0,0,-1], "origin": [0,0,0], "scale": [1,1,1], "units_to_meters": 1.0}, indent=2))
        try:
            print("[init] Loading mesh depth renderer. No Jev request has been sent.",flush=True)
            started = time.perf_counter()
            with defer_startup_interrupt():
                self.mesh = self._make_sim(str(stage), depth=True, color=rgb_mode == "mesh")
            if not self.mesh.pathfinder.load_nav_mesh(str(Path(cfg["scene_dir"])/"shuyuan.navmesh")):
                raise RuntimeError("motion NavMesh failed to load")
            print(f"[init] Mesh + NavMesh ready ({time.perf_counter()-started:.1f}s).",flush=True)
            if rgb_mode == "gs":
                gs_path = Path(cfg["scene_dir"])/"shuyuan.gs.ply"
                print(f"[init] Loading GS RGB ({gs_path.stat().st_size/1e9:.2f} GB) for replay. "
                      "This can take tens of seconds; missing semantic .scn warnings are not fatal here. "
                      "Ctrl+C during native initialization is deferred until this renderer finishes loading.",flush=True)
                started = time.perf_counter()
                with defer_startup_interrupt():
                    self.gs = self._make_sim(str(gs_path), depth=False, color=True)
                print(f"[init] GS RGB ready ({time.perf_counter()-started:.1f}s).",flush=True)
        except BaseException:
            self.close()
            raise

    def _make_sim(self, scene, depth, color):
        import magnum as mn
        h, c = self.h, self.cfg
        sim = h.SimulatorConfiguration()
        sim.scene_id, sim.gpu_device_id = scene, c["gpu_id"]
        sim.enable_physics, sim.create_renderer = False, True
        sim.navmesh_settings, sim.allow_sliding = None, c.get("allow_sliding",False)
        agent = h.agent.AgentConfiguration()
        agent.height, agent.radius = c["agent_height_m"], c["agent_radius_m"]
        specs = []
        for name, kind in [("depth", h.SensorType.DEPTH)]*int(depth) + [("rgb", h.SensorType.COLOR)]*int(color):
            spec = h.CameraSensorSpec()
            spec.uuid, spec.sensor_type = name, kind
            spec.resolution, spec.hfov = c["resolution"], c["hfov_deg"]
            spec.position = mn.Vector3(0, c["camera_height_m"], 0)
            spec.near, spec.far = c["near_m"], c["far_m"]
            if name == "depth":
                spec.channels = 1
            specs.append(spec)
        agent.sensor_specifications = specs
        agent.action_space = {name: h.agent.ActionSpec(name, h.agent.ActuationSpec(
            c["move_m"] if name.startswith("move_") else c["pitch_deg"] if name.startswith("look_") else c["turn_deg"]))
            for name in ACTIONS if name != "stop"}
        return h.Simulator(h.Configuration(sim, [agent]))

    def reset(self, task):
        from habitat_sim.utils.common import quat_from_angle_axis
        state = self.h.AgentState()
        state.position = np.asarray(task["start"], dtype=np.float32)
        state.rotation = quat_from_angle_axis(math.radians(task["yaw_deg"]), np.array([0,1,0]))
        self.mesh.get_agent(0).set_state(state)
        self.pitch = float(task.get("pitch_deg",0))
        self._sensor_pitch(self.mesh)
        self.observation = self.mesh.get_sensor_observations()

    def _sensor_pitch(self, sim):
        import magnum as mn
        for sensor in sim.get_agent(0).sensors.values():
            sensor.node.rotation = mn.Quaternion.rotation(mn.Deg(-self.pitch), mn.Vector3(1,0,0))

    def pose(self):
        from habitat_sim.utils.common import quat_rotate_vector
        state = self.mesh.get_agent(0).get_state()
        forward = quat_rotate_vector(state.rotation, np.array([0,0,-1]))
        yaw = math.atan2(-forward[0], -forward[2])
        return np.asarray(state.position).copy(), yaw

    def observe(self):
        depth = np.asarray(self.observation["depth"], dtype=np.float32).squeeze().copy()
        rgb = self.observation.get("rgb")
        if self.gs is not None:
            state = self.mesh.get_agent(0).get_state()
            copied = self.h.AgentState()
            copied.position, copied.rotation = state.position, state.rotation
            self.gs.get_agent(0).set_state(copied)
            self._sensor_pitch(self.gs)
            rgb = self.gs.get_sensor_observations()["rgb"]
        return depth, None if rgb is None else np.asarray(rgb)[...,:3].copy()

    def act(self, action):
        before, yaw = self.pose()
        old_pitch = self.pitch
        pitch = self.pitch + (self.cfg["pitch_deg"] if action == "look_down" else -self.cfg["pitch_deg"] if action == "look_up" else 0)
        valid = action in ACTIONS and self.cfg["pitch_min_deg"] <= pitch <= self.cfg["pitch_max_deg"]
        collided = False
        if valid and action != "stop":
            self.observation = self.mesh.step(action)
            collided = bool(self.observation["collided"])
            self.pitch = pitch
        after, new_yaw = self.pose()
        delta = relative(after, before, yaw)
        moved = float(np.linalg.norm(after-before))
        is_move = isinstance(action,str) and action.startswith("move_")
        success = valid and not collided and (not is_move or moved >= self.cfg["move_m"]*.95)
        return {"action": action, "valid": bool(valid), "success": bool(success), "collided": collided,
                "actual_translation_m": round(moved,4), "actual_forward_m": delta["forward_m"],
                "actual_left_m": delta["left_m"], "actual_yaw_deg": round(math.degrees(math.atan2(math.sin(new_yaw-yaw),math.cos(new_yaw-yaw))),3),
                "actual_pitch_deg": round(self.pitch-old_pitch,3),
                "result": "invalid_action_or_pitch_limit" if not valid else "collision" if collided else "executed"}

    def close(self):
        for sim in [self.gs, self.mesh]:
            if sim is not None:
                sim.close()
        self.gs = self.mesh = None
