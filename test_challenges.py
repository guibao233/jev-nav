import copy
from pathlib import Path
import tempfile
import unittest

from prepare_challenges import TIERS, matches_tier, route_geometry, write_bundle


class ChallengeGeometryTests(unittest.TestCase):
    def test_duplicates_do_not_create_bends_or_change_path(self):
        path = [[0, 0, 0], [0, 0, 0], [0, 0, -4], [0, 0, -8]]
        original = copy.deepcopy(path)
        result = route_geometry(path, 8.)
        self.assertEqual(result['significant_turns'], 0)
        self.assertAlmostEqual(result['geodesic_to_euclidean_ratio'], 1.)
        self.assertTrue(matches_tier(8., result, TIERS['control']))
        self.assertEqual(path, original)

    def test_l_bend_count_and_detour(self):
        result = route_geometry([[0, 0, 0], [0, 0, -4], [4, 0, -4]], 8.)
        self.assertEqual(result['significant_turns'], 1)
        self.assertEqual(result['turn_angles_deg'], [90.])
        self.assertAlmostEqual(result['geodesic_to_euclidean_ratio'], 2**.5)
        self.assertTrue(matches_tier(8., result, TIERS['turn']))
        self.assertFalse(matches_tier(8., result, TIERS['control']))

    def test_long_straight_does_not_qualify_as_complex(self):
        result = route_geometry([[0, 0, 0], [0, 0, -18]], 18.)
        self.assertFalse(matches_tier(18., result, TIERS['extended']))
        self.assertFalse(matches_tier(18., result, TIERS['control']))

    def test_u_turn_counts_two_bends(self):
        result = route_geometry([[0, 0, 0], [0, 0, -5], [2, 0, -5], [2, 0, 0]], 12.)
        self.assertEqual(result['significant_turns'], 2)
        self.assertAlmostEqual(result['total_abs_turn_deg'], 180.)
        self.assertAlmostEqual(result['geodesic_to_euclidean_ratio'], 6.)
        self.assertTrue(matches_tier(12., result, TIERS['long']))

    def test_bad_or_vertical_only_paths_rejected(self):
        for path in ([], [[0, 0, 0]], [[0, 0, 0], [0, 3, 0]], [[0, 0, 0], [float('nan'), 0, 2]]):
            with self.subTest(path=path), self.assertRaises(ValueError):
                route_geometry(path, 3.)

    def test_existing_bundle_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            sentinel = Path(folder)/'tasks.json'
            sentinel.write_text('original tasks')
            with self.assertRaises(FileExistsError):
                write_bundle(folder, {}, None, {})
            self.assertEqual(sentinel.read_text(), 'original tasks')


if __name__ == '__main__':
    unittest.main()
