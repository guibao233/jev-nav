"""CPU-only clearance-weighted reference paths on the existing flat NavMesh.

The NavMesh already accounts for the agent radius. Clearance here is additional
centre-to-NavMesh-boundary room, not a new collision radius or a mesh guarantee.
"""
import heapq
import math
import numpy as np
from core import RoutePreview
from environment import direct_navmesh_connection


VERSION = 'clearance_grid_v1'


def path_statistics(pf, points, sample_m=.025):
    route = RoutePreview(points)
    samples = np.array([route.at(s) for s in np.r_[np.arange(0, route.total, sample_m), route.total]])
    clearance = np.array([pf.distance_to_closest_obstacle(p, 2.) for p in samples])
    return {'length_m': route.total, 'vertices': len(route.points), 'sample_spacing_m': sample_m,
            'samples': len(samples), 'clearance_query_cap_m': 2.,
            'extra_navmesh_clearance_min_m': float(clearance.min()),
            'extra_navmesh_clearance_p10_m': float(np.percentile(clearance, 10)),
            'extra_navmesh_clearance_median_m': float(np.median(clearance)),
            'fraction_below_0_10_m': float(np.mean(clearance < .1)),
            'fraction_below_0_20_m': float(np.mean(clearance < .2))}


def validate_reference_path(pf, points, start, goal):
    route = RoutePreview(points)
    if not np.allclose(route.points[0], start, atol=1e-4, rtol=0) or not np.allclose(route.points[-1], goal, atol=1e-4, rtol=0):
        raise ValueError('clearance reference endpoints must match the task')
    for i, (a, b) in enumerate(zip(route.points, route.points[1:])):
        if not direct_navmesh_connection(pf, a, b):
            raise ValueError(f'clearance reference segment {i} is not directly navigable')
    return route.total


class ClearancePlanner:
    """Eight-neighbour A* with native-checked edges and exact endpoint links.

    Integral cost: length * (1 + weight * exp(-clearance / scale)). It is a
    soft preference: tight passages remain usable, without a hard erosion.
    Only a flat floor around the supplied shortest route is searched.
    """
    def __init__(self, pf, seed_path, grid_m=.1, clearance_m=.2, weight=4., padding_m=2.):
        values = [grid_m, clearance_m, padding_m]
        if any(not math.isfinite(x) or x <= 0 for x in values) or not math.isfinite(weight) or weight < 0:
            raise ValueError('grid, clearance scale and padding must be positive; weight must be nonnegative')
        self.pf, self.grid_m, self.scale, self.weight = pf, grid_m, clearance_m, weight
        route = RoutePreview(seed_path)
        if np.ptp(route.points[:, 1]) > .02:
            raise ValueError('this planner supports flat reference paths only (height span <= 0.02 m)')
        self.start, self.goal = route.points[0], route.points[-1]
        self.y = float(self.start[1])
        self.low = np.floor((route.points[:, [0, 2]].min(axis=0)-padding_m)/grid_m)*grid_m
        high = np.ceil((route.points[:, [0, 2]].max(axis=0)+padding_m)/grid_m)*grid_m
        self.shape = np.rint((high-self.low)/grid_m).astype(int)+1
        if int(np.prod(self.shape)) > 500000:
            raise ValueError('search grid too large; increase grid spacing or reduce padding')
        self.points, self._clearances, self._lines = {}, {}, {}
        for ix in range(self.shape[0]):
            for iz in range(self.shape[1]):
                p = np.array([self.low[0]+ix*grid_m, self.y, self.low[1]+iz*grid_m])
                if pf.is_navigable(p, .02):
                    self.points[(ix, iz)] = p
        self.parameters = {'version': VERSION, 'grid_m': grid_m, 'clearance_scale_m': clearance_m,
                           'weight': weight, 'padding_m': padding_m, 'height_span_limit_m': .02,
                           'edge_validation_spacing_m': .05, 'clearance_query_cap_m': 2.,
                           'cost': 'integral(1 + weight * exp(-extra_navmesh_clearance / clearance_scale_m)) ds',
                           'clearance_is_soft_preference': True}

    @staticmethod
    def _key(point):
        return tuple(np.round(point, 7))

    def clearance(self, point):
        key = self._key(point)
        if key not in self._clearances:
            self._clearances[key] = float(self.pf.distance_to_closest_obstacle(point, 2.))
        return self._clearances[key]

    def line(self, a, b):
        key = (self._key(a), self._key(b))
        if key in self._lines:
            return self._lines[key]
        if not direct_navmesh_connection(self.pf, a, b):
            self._lines[key] = None
            return None
        length = float(np.linalg.norm(b-a))
        count = max(1, int(math.ceil(length/.05)))
        distances = np.array([self.clearance(a+t*(b-a)) for t in np.linspace(0, 1, count+1)])
        density = 1 + self.weight*np.exp(-distances/self.scale)
        cost = length/count * float(np.sum((density[:-1]+density[1:])*.5))
        result = (length, cost, float(distances.min()))
        self._lines[key] = result
        return result

    def endpoint_links(self, position):
        nearby = sorted((float(np.linalg.norm(p-position)), node) for node, p in self.points.items()
                        if np.linalg.norm(p-position) <= max(.25, 2*self.grid_m))
        links = {}
        for _, node in nearby:
            edge = self.line(position, self.points[node])
            if edge is not None:
                links[node] = edge[1]
        if not links:
            raise ValueError('endpoint cannot connect to the grid; try finer --grid-m')
        return links

    def plan(self):
        start_id, goal_id = (-1, 0), (-2, 0)
        start_links = self.endpoint_links(self.start)
        # Goal links are checked in their actual traversal direction.
        goal_links = {node: edge[1] for node in self.endpoint_links(self.goal)
                      if (edge := self.line(self.points[node], self.goal)) is not None}
        if not goal_links:
            raise ValueError('no directly navigable goal connector')
        points = dict(self.points)
        points[start_id], points[goal_id] = self.start, self.goal
        scores, parents = {start_id: 0.}, {}
        queue = [(float(np.linalg.norm(self.goal-self.start)), 0., start_id)]
        expanded = 0
        while queue:
            _, cost, node = heapq.heappop(queue)
            if cost > scores[node]+1e-10:
                continue
            if node == goal_id:
                break
            expanded += 1
            if node == start_id:
                neighbors = start_links.items()
            else:
                neighbors = []
                for dx,dz in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
                    other = (node[0]+dx, node[1]+dz)
                    if other not in self.points:
                        continue
                    edge = self.line(points[node], points[other])
                    if edge is not None:
                        neighbors.append((other, edge[1]))
                if node in goal_links:
                    neighbors.append((goal_id, goal_links[node]))
            for other, edge_cost in neighbors:
                candidate = cost+edge_cost
                if candidate+1e-10 < scores.get(other, math.inf):
                    scores[other], parents[other] = candidate, node
                    heapq.heappush(queue, (candidate+float(np.linalg.norm(points[other]-self.goal)), candidate, other))
        if goal_id not in parents:
            raise ValueError('no grid route found; original NavMesh was not changed; try finer grid or wider padding')
        ids = [goal_id]
        while ids[-1] != start_id:
            ids.append(parents[ids[-1]])
        raw = np.array([points[node] for node in reversed(ids)])
        raw = raw[np.r_[True, np.linalg.norm(np.diff(raw, axis=0), axis=1)>1e-7]]
        edges = [self.line(a,b) for a,b in zip(raw,raw[1:])]
        prefix = np.r_[0., np.cumsum([e[1] for e in edges])]
        # Simplify only when native connectivity, weighted cost and the minimum
        # clearance of the replaced section are retained (<=5 mm clearance loss).
        selected, i = [raw[0]], 0
        while i < len(raw)-1:
            for j in range(len(raw)-1, i, -1):
                edge = self.line(raw[i], raw[j])
                if edge is not None and edge[1] <= (prefix[j]-prefix[i])*1.01+1e-8 and edge[2] >= min(e[2] for e in edges[i:j])-.005:
                    break
            selected.append(raw[j]);i=j
        path = np.array(selected)
        validate_reference_path(self.pf, path, self.start, self.goal)
        stats = {'grid_shape': self.shape.tolist(), 'navigable_grid_points': len(self.points),
                 'expanded_nodes': expanded, 'raw_vertices': len(raw), 'reference_vertices': len(path),
                 'raw_grid_weighted_cost': scores[goal_id],
                 'reference_weighted_cost': sum(self.line(a,b)[1] for a,b in zip(path,path[1:]))}
        return path.tolist(), stats
