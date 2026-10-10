"""Regressions for path reassociation and local-action summaries; no GPU/API."""
import math
import unittest
from unittest.mock import Mock
import numpy as np

from core import RoutePreview, recent_motion_summary
from environment import direct_navmesh_connection
from test_core import config


class WallPathfinder:
    """Two navigable half-planes separated by an impassable x=0.1 wall."""
    def is_navigable(self, point):
        return abs(point[0]-.1) > 1e-8

    def try_step(self, start, end):
        if (start[0]-.1)*(end[0]-.1) <= 0:
            return np.asarray(start)
        return np.asarray(end)


class ReassociationTests(unittest.TestCase):
    def test_lost_window_rejoins_later_segment_and_moves_target_ahead(self):
        route = RoutePreview([[0,0,0],[0,0,-5]], reconnect=lambda a,b: True)
        route.state([0,0,0],0,config())
        route.state([1.,0,-1.9],0,config())  # Leave the route, then approach a later part.
        state = route.state([.1,0,-2],0,config())
        self.assertEqual(state['tracking']['mode'],'reassociated')
        self.assertAlmostEqual(route.progress,2.)
        self.assertAlmostEqual(state['current_target']['forward_m'],.75)
        self.assertAlmostEqual(state['distance_from_local_reference_m'],.1)
        next_state = route.state([.1,0,-2],0,config())
        self.assertEqual(next_state['tracking']['mode'],'local')
        self.assertEqual(next_state['tracking']['reassociation_jump_m'],0)

    def test_nearby_branch_is_not_used_when_local_tracking_is_valid(self):
        checker=Mock(return_value=True)
        route=RoutePreview([[0,0,0],[0,0,-3],[.2,0,-3],[.2,0,0]], reconnect=checker)
        for _ in range(20):
            route.state([.19,0,0],0,config())
        self.assertLess(route.progress,.5)
        checker.assert_not_called()

    def test_wall_separating_close_route_point_prevents_reassociation(self):
        pf=WallPathfinder()
        self.assertTrue(pf.is_navigable([.2,0,-2]))
        self.assertTrue(pf.is_navigable([0,0,-2]))
        route=RoutePreview([[0,0,0],[0,0,-5]], reconnect=lambda a,b: direct_navmesh_connection(pf,a,b))
        state=route.state([.2,0,-2],0,config())
        self.assertEqual(route.progress,0.)
        self.assertEqual(state['tracking']['mode'],'off_path')

    def test_direct_connector_rejects_sliding_and_other_floor(self):
        pf=Mock()
        pf.is_navigable.return_value=True
        pf.try_step.side_effect=lambda start,end: np.asarray(end)+[.01,0,0]
        self.assertFalse(direct_navmesh_connection(pf,[0,0,0],[0,0,-.3]))
        pf.try_step.reset_mock()
        self.assertFalse(direct_navmesh_connection(pf,[0,0,0],[0,1,-.3]))
        pf.try_step.assert_not_called()

    def test_direct_connector_accepts_same_point_and_unobstructed_line(self):
        pf=WallPathfinder()
        self.assertTrue(direct_navmesh_connection(pf,[0,0,0],[0,0,0]))
        self.assertTrue(direct_navmesh_connection(pf,[0,0,0],[0,0,-.48]))

    def test_missing_checker_and_distant_route_do_not_reassociate(self):
        for callback,position in [(None,[.1,0,-2]),(lambda a,b: True,[1.,0,-2])]:
            route=RoutePreview([[0,0,0],[0,0,-5]], reconnect=callback)
            route.state(position,0,config())
            self.assertEqual(route.progress,0.)

    def test_reassociated_progress_never_rewinds_and_preserves_corner(self):
        route=RoutePreview([[0,0,0],[0,0,-2.2],[2,0,-2.2]], reconnect=lambda a,b: True)
        state=route.state([.1,0,-2],0,config())
        self.assertEqual(state['tracking']['mode'],'reassociated')
        self.assertAlmostEqual(state['current_target']['forward_m'],.2)
        self.assertFalse(state['current_target']['is_final'])
        self.assertTrue(any(abs(p['forward_m']-.2)<1e-4 and abs(p['left_m']-.1)<1e-4 for p in state['ordered_preview']))
        route.state([0,0,-1.0],0,config())
        self.assertGreaterEqual(route.progress,2.)


def outcome(forward=0.,left=0.,yaw=0.,valid=True,collided=False):
    return {'actual_forward_m':forward,'actual_left_m':left,'actual_translation_m':math.hypot(forward,left),
            'actual_yaw_deg':yaw,'valid':valid,'collided':collided,'success':valid and not collided}


class RecentMotionTests(unittest.TestCase):
    def test_short_history_does_not_claim_stagnation(self):
        for history in [[],[outcome(yaw=15),outcome(yaw=-15)]]:
            summary=recent_motion_summary(history)
            self.assertEqual(summary['status'],'insufficient_history')
            self.assertFalse(summary['low_net_motion'])

    def test_five_opposite_turns_are_oscillation_despite_execution_success(self):
        summary=recent_motion_summary([outcome(yaw=y) for y in [15,-15,15,-15,15]])
        self.assertEqual(summary['status'],'turn_oscillation')
        self.assertEqual(summary['opposite_turn_pairs'],4)
        self.assertEqual(summary['net_translation_m'],0.)
        self.assertEqual(summary['net_turn_deg'],15.)
        self.assertEqual(summary['execution_success_count'],5)

    def test_consistent_rotation_is_observation_not_turn_oscillation(self):
        summary=recent_motion_summary([outcome(yaw=15)]*5)
        self.assertEqual(summary['status'],'no_translation')
        self.assertEqual(summary['opposite_turn_pairs'],0)
        self.assertEqual(summary['net_turn_deg'],75.)

    def test_translation_composes_body_rotations_instead_of_summing_local_axes(self):
        summary=recent_motion_summary([outcome(forward=.25),outcome(yaw=90),outcome(forward=.25),outcome(yaw=90),outcome(forward=.25)])
        self.assertAlmostEqual(summary['net_translation_m'],.25)
        self.assertAlmostEqual(summary['travelled_m'],.75)
        self.assertEqual(summary['status'],'moving')

    def test_return_to_start_after_rotation_is_low_net_motion(self):
        summary=recent_motion_summary([outcome(forward=.25),outcome(yaw=90),outcome(yaw=90),outcome(forward=.25),outcome()])
        self.assertEqual(summary['status'],'low_net_motion')
        self.assertAlmostEqual(summary['net_translation_m'],0.)
        self.assertAlmostEqual(summary['travelled_m'],.5)

    def test_only_last_window_is_used_and_execution_failures_are_counted(self):
        prefix=[outcome(yaw=15,valid=False,collided=True)]*20
        recent=[outcome(forward=.25)]*5
        self.assertEqual(recent_motion_summary(prefix+recent),recent_motion_summary(recent))
        mixed=recent_motion_summary([outcome(valid=False),outcome(collided=True),outcome(),outcome(),outcome()])
        self.assertEqual(mixed['invalid_action_count'],1)
        self.assertEqual(mixed['collision_count'],1)
        self.assertEqual(mixed['execution_success_count'],3)


if __name__=='__main__':
    unittest.main()
