"""Coordinate/provenance checks for offline overlays; no simulator or API."""
import math
import unittest

from map_view import map_view, panel_pixel, recorded_targets, relative_to_world


class MapViewTests(unittest.TestCase):
    def test_inverse_body_coordinates_at_known_headings(self):
        point = {"forward_m":2.,"left_m":1.}
        for yaw,expected in [(0,[9,3,18]),(math.pi/2,[8,3,21]),(-math.pi/2,[12,3,19])]:
            with self.subTest(yaw=yaw):
                got = relative_to_world(point,{"position":[10,3,20],"yaw_rad":yaw})
                for a,b in zip(got,expected): self.assertAlmostEqual(a,b)

    def test_uses_logged_targets_and_observation_pose(self):
        r = {"pose":{"position":[1,0,2],"yaw_rad":0},"request":{"state":{"reference":{
            "current_target":{"forward_m":.75,"left_m":-.25},
            "ordered_preview":[{"forward_m":.5,"left_m":0},{"forward_m":1.,"left_m":.25}]}}}}
        got = recorded_targets(r)
        self.assertEqual(got["current_target_world"],[1.25,0,1.25])
        self.assertEqual(got["ordered_preview_world"],[[1,0,1.5],[.75,0,1.]])

    def test_terminal_observation_has_no_invented_target(self):
        self.assertEqual(recorded_targets({"request":None}),
            {"current_target_world":None,"ordered_preview_world":[]})

    def test_map_axes_and_crop_contain_endpoints(self):
        m = {"map":{"origin_x":-10,"origin_z":-20,"resolution_m":.05},
             "task":{"start":[0,0,0],"goal":[0,0,-4],"path":[[0,0,0],[0,0,-4]]}}
        view = map_view(m,[])
        start,goal = [panel_pixel(m["task"][k],m,view) for k in ["start","goal"]]
        self.assertAlmostEqual(start[0],goal[0])
        self.assertLess(goal[1],start[1])
        for x,y in [start,goal]:
            self.assertTrue(12<x<628 and 8<y<408)
        self.assertGreater(panel_pixel([1,0,0],m,view)[0],start[0])


if __name__ == "__main__":
    unittest.main()
