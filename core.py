"""Pure geometry. Body convention: forward = -Z, left = -X, yaw positive left.

Only RoutePreview uses the reference path. Depth facts never query a NavMesh.
Camera pitch is positive DOWN; target bearings are independent of pitch.
"""
import math
import numpy as np


def relative(point, position, yaw):
    d = np.asarray(point) - np.asarray(position)
    forward = -d[0] * math.sin(yaw) - d[2] * math.cos(yaw)
    left = -d[0] * math.cos(yaw) + d[2] * math.sin(yaw)
    return {"forward_m": round(float(forward), 3),
            "left_m": round(float(left), 3),
            "distance_m": round(float(math.hypot(forward, left)), 3),
            "bearing_deg": round(math.degrees(math.atan2(left, forward)), 2)}


class RoutePreview:
    """Monotone tracking on the fixed route, with optional checked reassociation.

    Normal tracking uses the original local window. If that window is lost,
    reconnect validates a direct NavMesh connection to a nearby later segment.
    No connection checker means no reassociation. The route is never replanned.
    """
    VERSION = "checked_reassociation_v1"
    MAX_REFERENCE_DISTANCE_M = .5

    def __init__(self, points, reconnect=None):
        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2 or pts.shape[1] != 3 or len(pts) < 2 or not np.isfinite(pts).all():
            raise ValueError("path must contain at least two finite XYZ points")
        keep = np.r_[True, np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-6]
        self.points = pts[keep]
        if len(self.points) < 2:
            raise ValueError("zero-length path")
        self.lengths = np.linalg.norm(np.diff(self.points, axis=0), axis=1)
        self.arcs = np.r_[0., np.cumsum(self.lengths)]
        self.progress = 0.
        self.previous_position = None
        self.reconnect = reconnect
        self.tracking = {"mode": "local", "progress_m": 0., "reassociation_jump_m": 0.}

    @property
    def total(self):
        return float(self.arcs[-1])

    def at(self, arc):
        arc = float(np.clip(arc, 0, self.total))
        i = min(np.searchsorted(self.arcs, arc, side="right") - 1, len(self.lengths) - 1)
        return self.points[i] + (arc - self.arcs[i]) / self.lengths[i] * (self.points[i+1] - self.points[i])

    def update(self, position, step_m):
        pos = np.asarray(position, dtype=float)
        moved = 0. if self.previous_position is None else float(np.linalg.norm(pos - self.previous_position))
        previous_progress = self.progress
        mode = "local"
        # Preserve local tracking near the route; do not switch nearby branches.
        limit = min(self.total, self.progress + max(step_m + .15, moved + .15))
        best = (float("inf"), self.progress)
        for i, length in enumerate(self.lengths):
            lo, hi = max(self.progress, self.arcs[i]), min(limit, self.arcs[i+1])
            if lo > hi:
                continue
            direction = (self.points[i+1] - self.points[i]) / length
            s = float(np.clip(self.arcs[i] + np.dot(pos - self.points[i], direction), lo, hi))
            dist = float(np.linalg.norm(pos - self.at(s)))
            if (dist, s) < best:
                best = dist, s
        if best[0] <= self.MAX_REFERENCE_DISTANCE_M:
            self.progress = max(self.progress, best[1])
        else:
            mode = "off_path"
            if self.reconnect is not None:
                candidates = []
                for i, length in enumerate(self.lengths):
                    lo, hi = max(limit, self.arcs[i]), self.arcs[i+1]
                    if lo > hi:
                        continue
                    direction = (self.points[i+1] - self.points[i]) / length
                    arc = float(np.clip(self.arcs[i] + np.dot(pos - self.points[i], direction), lo, hi))
                    point = self.at(arc)
                    distance = float(np.linalg.norm(pos-point))
                    if distance <= self.MAX_REFERENCE_DISTANCE_M and arc > limit + 1e-6:
                        candidates.append((distance, arc))
                # Nearest connectable segment first; prefer the earlier arc at ties.
                for distance, arc in sorted(candidates):
                    if self.reconnect(pos, self.at(arc)):
                        self.progress = arc
                        best = distance, arc
                        mode = "reassociated"
                        break
        self.tracking = {"mode": mode, "progress_m": round(self.progress, 3),
                         "reassociation_jump_m": round(self.progress-previous_progress, 3) if mode == "reassociated" else 0.}
        self.previous_position = pos.copy()
        return best[0]

    def state(self, position, yaw, cfg):
        lateral = self.update(position, cfg["move_m"])
        end = min(self.total, self.progress + cfg["preview_m"])
        arcs = list(np.arange(self.progress + cfg["sample_spacing_m"], end, cfg["sample_spacing_m"]))
        arcs += [float(s) for s in self.arcs[1:-1] if self.progress + .05 < s <= end]
        arcs.append(end)
        target_s = min(self.total, self.progress + cfg["target_lookahead_m"])
        corners = [float(s) for s in self.arcs[1:-1] if s > self.progress + .12]
        if corners:
            target_s = min(target_s, corners[0])
        self.current_target_point = self.at(target_s)
        target = relative(self.current_target_point, position, yaw)
        target["is_final"] = abs(target_s - self.total) < 1e-6
        samples = []
        for arc in sorted(set(round(s, 5) for s in arcs)):
            item = relative(self.at(arc), position, yaw)
            item["ahead_along_path_m"] = round(arc - self.progress, 3)
            samples.append(item)
        return {"current_target": target, "ordered_preview": samples,
                "final_goal": relative(self.points[-1], position, yaw),
                "distance_from_local_reference_m": round(lateral, 3),
                "remaining_reference_length_m": round(self.total - self.progress, 3),
                "tracking": dict(self.tracking)}


def recent_motion_summary(history, window_steps=5, move_m=.25):
    """Summarize own executed deltas only, composing their changing body frames.

    No goal, route, depth, or world-map history is read. A turn can execute
    successfully while producing no translation; useful observation is not failure.
    """
    recent = history[-window_steps:]
    displacement = np.zeros(2)  # forward, left in the window's initial body frame
    heading = travelled = absolute_turn = 0.
    turn_deltas = []
    for outcome in recent:
        forward, left = outcome["actual_forward_m"], outcome["actual_left_m"]
        c, s = math.cos(heading), math.sin(heading)
        displacement += [forward*c-left*s, forward*s+left*c]
        yaw = outcome["actual_yaw_deg"]
        heading += math.radians(yaw)
        absolute_turn += abs(yaw)
        travelled += outcome["actual_translation_m"]
        turn_deltas.append(yaw)
    reversals = sum(a*b < 0 for a,b in zip(turn_deltas, turn_deltas[1:]))
    net = float(np.linalg.norm(displacement))
    full = len(recent) == window_steps
    threshold = max(.02, move_m*.2)
    low_net_motion = full and net <= threshold
    if not full:
        status = "insufficient_history"
    elif low_net_motion and reversals >= 2:
        status = "turn_oscillation"
    elif low_net_motion and travelled <= threshold:
        status = "no_translation"
    elif low_net_motion:
        status = "low_net_motion"
    else:
        status = "moving"
    return {"source": "recent_own_action_outcomes_only", "window_steps": len(recent),
            "window_capacity": window_steps, "status": status,
            "net_translation_m": round(net, 4), "travelled_m": round(travelled, 4),
            "net_turn_deg": round(math.degrees(heading), 3),
            "absolute_turn_deg": round(absolute_turn, 3), "opposite_turn_pairs": reversals,
            "collision_count": sum(bool(o["collided"]) for o in recent),
            "invalid_action_count": sum(not o["valid"] for o in recent),
            "execution_success_count": sum(bool(o["success"]) for o in recent),
            "low_net_motion": low_net_motion,
            "note": "Action success means execution succeeded, not navigation progress. No translation alone can be useful observation."}


def depth_points(depth, pitch_deg, cfg):
    """Return right, height above feet, forward (metres) from camera optical-Z depth."""
    z = np.asarray(depth, dtype=np.float32)
    h, w = z.shape
    f = w / (2 * math.tan(math.radians(cfg["hfov_deg"] / 2)))
    x = (np.arange(w)[None, :] - (w-1)/2) / f * z
    y = (np.arange(h)[:, None] - (h-1)/2) / f * z
    c, s = math.cos(math.radians(pitch_deg)), math.sin(math.radians(pitch_deg))
    return x, cfg["camera_height_m"] - (y*c + z*s), z*c - y*s


def _sweep_mask(x, forward, vector, step, radius):
    """Footprint of a capsule translating one step in an egocentric direction."""
    along = x * vector[0] + forward * vector[1]
    across = x * vector[1] - forward * vector[0]
    return across**2 + (along - np.clip(along, 0, step))**2 <= radius**2


def _sweep_visibility(depth, pitch, vector, cfg):
    """Conservative sampled-volume ray visibility, not a proof of free space.

    All probes in the newly swept body volume must project into valid depth and
    lie in front of a measured surface. Missing/occluded probes mean unknown.
    """
    radius = cfg["agent_radius_m"] + cfg["geometry_margin_m"]
    step = cfg["move_m"]
    a = np.linspace(-radius, step + radius, 12)
    b = np.linspace(-radius, radius, 7)
    along, across = np.meshgrid(a, b)
    sel = ((along - np.clip(along, 0, step))**2 + across**2 <= radius**2 + 1e-9)
    sel &= along**2 + across**2 > radius**2 + 1e-9
    x = along[sel]*vector[0] + across[sel]*vector[1]
    fwd = along[sel]*vector[1] - across[sel]*vector[0]
    heights = np.linspace(cfg["obstacle_min_height_m"], cfg["agent_height_m"]-.03, 10)
    x = np.repeat(x, len(heights))
    fwd = np.repeat(fwd, len(heights))
    down = cfg["camera_height_m"] - np.tile(heights, len(x)//len(heights))
    c, s = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    yc, zc = down*c - fwd*s, down*s + fwd*c
    h, w = depth.shape
    focal = w / (2*math.tan(math.radians(cfg["hfov_deg"]/2)))
    u = np.rint(focal*x/np.maximum(zc, 1e-6)+(w-1)/2).astype(int)
    v = np.rint(focal*yc/np.maximum(zc, 1e-6)+(h-1)/2).astype(int)
    inside = (zc > cfg["near_m"]) & (u >= 1) & (u < w-1) & (v >= 1) & (v < h-1)
    observed = np.zeros(len(x), dtype=bool)
    ids = np.flatnonzero(inside)
    if len(ids):
        # Small neighborhood minimum makes foreground edges conservative.
        patches = np.stack([depth[v[ids]+dv, u[ids]+du] for dv in [-1,0,1] for du in [-1,0,1]])
        good = np.isfinite(patches) & (patches > cfg["near_m"]) & (patches < cfg["far_m"]*.999)
        measured = np.min(np.where(good, patches, np.inf), axis=0)
        observed[ids] = good.all(axis=0) & (measured > zc[ids] + cfg["geometry_margin_m"])
    return float(observed.mean()) if len(observed) else 0.


def depth_facts(depth, pitch, cfg):
    depth = np.asarray(depth)
    valid = np.isfinite(depth) & (depth > cfg["near_m"]) & (depth < cfg["far_m"]*.999)
    x, height, fwd = depth_points(depth, pitch, cfg)
    obstacle = valid & (height > cfg["obstacle_min_height_m"]) & (height < cfg["agent_height_m"]+.03)
    # Suppress isolated single pixels, retaining even narrow supported obstacles.
    padded = np.pad(obstacle.astype(np.uint8), 1)
    support = sum(padded[i:i+depth.shape[0], j:j+depth.shape[1]] for i in range(3) for j in range(3))
    obstacle &= support >= 3
    distance = np.hypot(x, fwd)
    bearing = np.degrees(np.arctan2(-x, fwd))
    floor = valid & (np.abs(height) < .10)
    edges = np.linspace(-cfg["hfov_deg"]/2, cfg["hfov_deg"]/2, cfg["sectors"]+1)
    sectors = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        angular = (bearing >= lo) & (bearing < hi) & (fwd > 0)
        obs = obstacle & angular
        measured = valid & angular
        sectors.append({"bearing_interval_deg": [round(float(lo),1),round(float(hi),1)],
            "nearest_obstacle_m": round(float(distance[obs].min()),2) if obs.any() else None,
            "observation": "obstacle_seen" if obs.any() else ("no_obstacle_seen" if measured.any() else "unknown"),
            "observed_surface_range_p90_m": round(float(np.percentile(distance[measured],90)),2) if measured.any() else None,
            "near_floor_seen": bool(np.count_nonzero(floor & angular & (distance < .6)) >= 3)})
    moves = {}
    for name, vector in {"move_forward": (0,1), "move_backward": (0,-1)}.items():
        mask = _sweep_mask(x, fwd, vector, cfg["move_m"], cfg["agent_radius_m"]+cfg["geometry_margin_m"])
        count = int(np.count_nonzero(obstacle & mask))
        coverage = _sweep_visibility(depth, pitch, vector, cfg)
        moves[name] = {"status": "blocked" if count >= 3 else ("clear" if coverage == 1. else "unknown"),
                       "swept_volume_observed_fraction": round(coverage,3)}
    return {"source": "current_mesh_depth_only", "valid_fraction": round(float(valid.mean()),3),
            "sectors": sectors, "move_checks": moves,
            "note": "No obstacle seen is not confirmed free space. Clear is a sampled geometric estimate; unseen volume is unknown."}
