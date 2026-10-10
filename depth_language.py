"""Language-only encoding of the existing nine mesh-depth sectors; no geometry changes."""
import math

DEPTH_FORMATS = ('numeric', 'semantic')
SEMANTIC_VERSION = 'nine_sectors_language_v1'
# Upper bounds inclusive; applies to already logged, rounded horizontal distances.
DISTANCE_BANDS = ((.5, 'very close'), (1., 'close'), (2., 'moderately near'), (4., 'far'))
# core.depth_facts orders sectors from negative bearing (right) to positive (left).
DIRECTIONS = ('right edge of forward view', 'outer right-front', 'right-front',
              'slightly right of ahead', 'straight ahead', 'slightly left of ahead',
              'left-front', 'outer left-front', 'left edge of forward view')


def depth_format(cfg):
    value = cfg.get('depth_format', 'numeric')
    if value not in DEPTH_FORMATS:
        raise ValueError("depth_format must be 'numeric' or 'semantic'")
    return value


def distance_band(value):
    if value is None:
        return 'unknown'
    if isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError('depth distance must be finite and nonnegative')
    for limit, label in DISTANCE_BANDS:
        if value <= limit:
            return label
    return 'very far'


def coverage_label(value):
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('depth coverage must be between zero and one')
    return 'not observed' if value == 0 else 'fully sampled' if value == 1 else 'partly observed'


def semantic_depth(facts):
    sectors = facts['sectors']
    if len(sectors) != len(DIRECTIONS):
        raise ValueError('semantic depth requires nine sectors')
    rows = []
    for direction, sector in zip(DIRECTIONS, sectors):
        observation = sector['observation']
        if observation not in ('obstacle_seen', 'no_obstacle_seen', 'unknown'):
            raise ValueError('invalid depth observation')
        band = distance_band(sector['nearest_obstacle_m']) if observation == 'obstacle_seen' else 'unknown'
        description = (f'Observed obstacle is {band}.' if band != 'unknown' else 'Obstacle detected; distance unknown.') if observation == 'obstacle_seen' else (
            'No obstacle detected in current observations; unobserved obstacles may exist.' if observation == 'no_obstacle_seen'
            else 'No valid observations; obstacle distance unknown.')
        rows.append({'direction': direction, 'observation': observation, 'distance_band': band,
                     'description': description,
                     'observed_surface_range': distance_band(sector['observed_surface_range_p90_m']),
                     'near_floor': 'nearby floor seen' if sector['near_floor_seen'] else 'nearby floor not confirmed visible'})
    descriptions = {'blocked':'An obstacle is observed in the next movement volume.',
                    'unknown':'The movement volume is not fully observed; safety is unknown.',
                    'clear':'Sampled movement volume appears free; this is not a safety guarantee.'}
    moves = {}
    for action, check in facts['move_checks'].items():
        status = check['status']
        if status not in descriptions:
            raise ValueError('invalid movement observation')
        moves[action] = {'status':status, 'description':descriptions[status],
                         'coverage':coverage_label(check['swept_volume_observed_fraction'])}
    return {'source':'current_mesh_depth_only','format':'semantic',
            'valid_observation_coverage':coverage_label(facts['valid_fraction']),
            'sectors':rows,'move_checks':moves,
            'note':'Directions refer only to the forward camera view, not the full surroundings. '
                   'Distance bands describe observed obstacles, not traversable distance. '
                   'Observed surface range is separate from obstacle distance. '
                   'No obstacle detected and unknown never mean confirmed free space.'}
