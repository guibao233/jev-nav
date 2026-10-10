"""Initial pose regressions: coordinate convention, first corner, source integrity."""
import copy
import math
from pathlib import Path
import tempfile
import unittest

from prepare_initial_heading import align_task, build_dataset, main, write_bundle

CFG = {'move_m': .25, 'preview_m': 3., 'sample_spacing_m': .5, 'target_lookahead_m': .75}


def task(path, yaw=135., identifier='test'):
    return {'id': identifier, 'start': path[0], 'goal': path[-1], 'path': path,
            'yaw_deg': yaw, 'pitch_deg': 15., 'geodesic_m': 5.,
            'shortest_path': copy.deepcopy(path), 'reference_path_kind': 'clearance_weighted'}


class InitialHeadingTests(unittest.TestCase):
    def test_habitat_heading_convention_in_all_quadrants(self):
        for x, z in [(0,-2), (-2,-2), (-2,0), (-2,2), (0,2), (2,2), (2,0), (2,-2)]:
            with self.subTest(x=x, z=z):
                source = task([[0,0,0], [x,0,z]], yaw=-170.)
                result = align_task(source, CFG)
                heading = math.radians(result['yaw_deg'])
                # Habitat body forward is local -Z, yaw positive about +Y.
                forward = (-math.sin(heading), -math.cos(heading))
                length = math.hypot(x,z)
                self.assertAlmostEqual(forward[0], x/length)
                self.assertAlmostEqual(forward[1], z/length)
                self.assertAlmostEqual(result['initial_heading']['target_after']['bearing_deg'], 0.)

    def test_first_corner_target_takes_priority_over_final_goal(self):
        source = task([[0,0,0], [0,0,-.4], [4,0,-.4]])
        result = align_task(source, CFG)
        self.assertEqual(result['yaw_deg'], 0.)
        self.assertEqual(result['initial_heading']['target_after']['distance_m'], .4)
        self.assertFalse(result['initial_heading']['target_after']['is_final'])

    def test_short_path_and_initial_projection_use_runtime_target(self):
        source = task([[0,0,0], [0,0,-.1], [2,0,-.1]])
        long = align_task(source, CFG)
        short = align_task(source, dict(CFG, target_lookahead_m=.05))
        self.assertEqual(short['yaw_deg'], 0.)
        # Existing tracker skips corners within 0.12 m: target is (0.65, 0, -0.1).
        self.assertAlmostEqual(long['yaw_deg'], math.degrees(math.atan2(-.65,.1)), delta=.0051)
        final = align_task(task([[0,0,0],[.2,0,0]]), CFG)
        self.assertEqual(final['yaw_deg'], -90.)
        self.assertTrue(final['initial_heading']['target_after']['is_final'])

    def test_source_and_non_heading_fields_preserved(self):
        source = {'tasks': [task([[0,0,0], [2,0,0]]),
                            task([[0,0,0], [0,0,-2]], identifier='other')],
                  'source_tasks': {'path':'clearance-source.json'}, 'assets': {'hash':'unchanged'}}
        before = copy.deepcopy(source)
        result = build_dataset(source, CFG, ['test'])
        self.assertEqual(source, before)
        self.assertEqual(len(result['tasks']), 1)
        original, aligned = source['tasks'][0], result['tasks'][0]
        self.assertEqual({k:v for k,v in aligned.items() if k != 'initial_heading' and k != 'yaw_deg'},
                         {k:v for k,v in original.items() if k != 'yaw_deg'})
        self.assertEqual(result['source_tasks'], source['source_tasks'])
        self.assertEqual(result, build_dataset(source, CFG, ['test']))

    def test_bad_heading_zero_horizontal_target_and_bad_selection_rejected(self):
        source = task([[0,0,0], [0,0,-1]])
        for bad in [dict(source, yaw_deg=float('nan')), task([[0,0,0],[0,1,0]]),
                    dict(source, start=[10,0,0])]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                align_task(bad, CFG)
        for selected in [[], ['missing']]:
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                build_dataset({'tasks':[source]}, CFG, selected)

    def test_existing_output_preserved_before_source_or_environment_access(self):
        with tempfile.TemporaryDirectory() as folder:
            sentinel = Path(folder)/'tasks.json'
            sentinel.write_text('original')
            with self.assertRaises(FileExistsError):
                main(['--tasks','nonexistent.json','--out',folder])
            with self.assertRaises(FileExistsError):
                write_bundle(folder, {})
            self.assertEqual(sentinel.read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
