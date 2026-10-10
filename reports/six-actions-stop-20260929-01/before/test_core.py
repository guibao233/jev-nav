"""Numerical/contract regressions; no renderer, network, API key, or extra deps."""
import json
import io
import math
import signal
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error
import numpy as np

from core import RoutePreview, depth_points, depth_facts, relative
from environment import defer_startup_interrupt
from jev import JevClient, ServiceFailure, make_request
from run import stop_status


def config():
    cfg = json.loads(Path(__file__).with_name("config.json").read_text())
    cfg.update(agent_radius_m=.1,agent_height_m=1.5)
    return cfg


class GeometryTests(unittest.TestCase):
    def test_body_bearings_and_rotation(self):
        self.assertEqual(relative([0,0,-2],[0,0,0],0)["bearing_deg"],0)
        self.assertEqual(relative([-2,0,0],[0,0,0],0)["bearing_deg"],90)
        self.assertAlmostEqual(relative([-2,0,0],[0,0,0],math.pi/2)["forward_m"],2)
        self.assertEqual(relative([2,0,0],[0,0,0],0)["bearing_deg"],-90)

    def test_floor_removed_after_pitch_alignment(self):
        cfg = config()
        h,w = 120,160
        f = w/2/math.tan(math.radians(cfg["hfov_deg"]/2))
        ray = (np.arange(h)[:,None]-(h-1)/2)/f
        pitch = math.radians(35)
        depth = np.broadcast_to(cfg["camera_height_m"]/(ray*math.cos(pitch)+math.sin(pitch)),(h,w)).copy()
        depth[(depth <= cfg["near_m"]) | (depth >= cfg["far_m"])] = np.nan
        _,height,_ = depth_points(depth,35,cfg)
        self.assertLess(float(np.nanmax(np.abs(height))),1e-5)
        facts = depth_facts(depth,35,cfg)
        self.assertTrue(all(s["nearest_obstacle_m"] is None for s in facts["sectors"]))

    def test_missing_depth_never_means_clear(self):
        facts = depth_facts(np.zeros((120,160)),0,config())
        self.assertEqual(facts["valid_fraction"],0)
        self.assertTrue(all(v["status"]=="unknown" for v in facts["move_checks"].values()))
        json.dumps(facts,allow_nan=False)

    def test_close_wall_blocks_front_not_back(self):
        facts = depth_facts(np.full((120,160),.20),0,config())
        self.assertEqual(facts["move_checks"]["move_forward"]["status"],"blocked")
        self.assertEqual(facts["move_checks"]["move_backward"]["status"],"unknown")

    def test_far_wall_does_not_prove_unseen_floor_clear(self):
        facts = depth_facts(np.full((120,160),3.),0,config())
        self.assertEqual(facts["move_checks"]["move_forward"]["status"],"unknown")
        self.assertTrue(all(not x["near_floor_seen"] for x in facts["sectors"]))

    def test_corner_is_current_target_and_preserved_in_preview(self):
        route = RoutePreview([[0,0,0],[0,0,-1],[2,0,-1]])
        facts = route.state([0,0,-.6],0,config())
        self.assertAlmostEqual(facts["current_target"]["left_m"],0)
        self.assertFalse(facts["current_target"]["is_final"])
        self.assertTrue(any(abs(x["left_m"]) < 1e-6 for x in facts["ordered_preview"]))

    def test_nearby_future_branch_does_not_skip_route(self):
        route = RoutePreview([[0,0,0],[0,0,-3],[.2,0,-3],[.2,0,0]])
        route.state([.19,0,0],0,config())
        self.assertLess(route.progress,.5)
        for _ in range(20):
            route.state([.19,0,0],0,config())
        self.assertLess(route.progress,.5)

    def test_forward_progress_never_rewinds(self):
        route = RoutePreview([[0,0,0],[0,0,-3]])
        for distance in [0,.25,.5,.75]:
            route.state([0,0,-distance],0,config())
        route.state([0,0,-.4],0,config())
        self.assertAlmostEqual(route.progress,.75)

    def test_stop_is_required_and_checked_at_final_goal(self):
        self.assertIsNone(stop_status("move_forward",.1,.3))
        self.assertEqual(stop_status("stop",.3,.3),"success")
        self.assertEqual(stop_status("stop",2.,.3),"early_stop")
        self.assertEqual(stop_status("stop",None,.3),"early_stop")


class StartupTests(unittest.TestCase):
    def test_interrupt_waits_until_constructor_result_is_owned(self):
        previous = signal.getsignal(signal.SIGINT)
        owned = []
        with self.assertRaises(KeyboardInterrupt):
            with defer_startup_interrupt():
                # Simulate repeated Ctrl+C while a native constructor is running.
                signal.raise_signal(signal.SIGINT)
                signal.raise_signal(signal.SIGINT)
                owned.append("completed simulator")
        self.assertEqual(owned,["completed simulator"])
        self.assertIs(signal.getsignal(signal.SIGINT),previous)

    def test_constructor_error_preserved_and_handler_restored(self):
        previous = signal.getsignal(signal.SIGINT)
        with self.assertRaisesRegex(RuntimeError,"renderer failed"):
            with defer_startup_interrupt():
                signal.raise_signal(signal.SIGINT)
                raise RuntimeError("renderer failed")
        self.assertIs(signal.getsignal(signal.SIGINT),previous)


class ApiTests(unittest.TestCase):
    def test_nine_actions_payload_does_not_include_key(self):
        payload = make_request({"test":True},config())
        self.assertEqual(len(payload["questions"]["action"]["criteria"]),9)
        self.assertEqual(payload["questions"]["action"]["type"],"choice")
        self.assertNotIn("Authorization",json.dumps(payload))

    def test_no_key_fails_without_network(self):
        # A TypeSafe credential must not be sent to OpenRouter accidentally.
        with patch.dict("os.environ",{"TYPESAFE_API_KEY":"legacy-key"},clear=True),patch("urllib.request.urlopen") as call:
            with self.assertRaisesRegex(ValueError,"OPENROUTER_API_KEY"):
                JevClient(config())
            call.assert_not_called()

    def test_successful_http_contract(self):
        response = {"id":"test-only","model":"typesafe/jev-1.13-20260917","provider":"TypeSafe",
            "answers":{"action":{"type":"choice","choice":"stop","probabilities":{"stop":1.},"confidence":1.}},
            "usage":{"input_tokens":100,"output_tokens":0,"cost":0.0000042}}
        state = {"robot":{"camera_pitch_deg":15},"recent_actions":[]}
        payload = make_request(state,config())
        with patch.dict("os.environ",{"OPENROUTER_API_KEY":"unit-test-placeholder"},clear=True),patch("urllib.request.urlopen",return_value=io.BytesIO(json.dumps(response).encode())) as call:
            result = JevClient(config()).decide(payload)
        request = call.call_args.args[0]
        self.assertEqual(request.full_url,"https://openrouter.ai/api/alpha/decisions")
        self.assertEqual(request.get_method(),"POST")
        self.assertEqual(request.get_header("Authorization"),"Bearer unit-test-placeholder")
        body = json.loads(request.data)
        self.assertEqual(body,payload)
        self.assertEqual(body["state"],state)
        self.assertEqual(body["model"],"typesafe/jev-1.13")
        self.assertNotIn("unit-test-placeholder",json.dumps([body,result]))
        self.assertEqual(result["choice"],"stop")
        self.assertEqual(result["api_provider"],"openrouter")
        self.assertEqual(result["response"],response)

    def test_auth_failure_not_retried_or_logged_with_secret(self):
        cfg = config()
        for status in [401,402]:
            with self.subTest(status=status):
                error = urllib.error.HTTPError("https://openrouter.ai/api/alpha/decisions",status,"secret-must-not-appear",{},None)
                with patch.dict("os.environ",{"OPENROUTER_API_KEY":"secret-must-not-appear"},clear=True),patch("urllib.request.urlopen",side_effect=error) as call:
                    with self.assertRaises(ServiceFailure) as caught:
                        JevClient(cfg).decide(make_request({},cfg))
                    self.assertEqual(call.call_count,1)
                    self.assertIn(f"HTTP {status}",str(caught.exception))
                    self.assertNotIn("secret-must-not-appear",str(caught.exception))

    def test_malformed_answer_is_service_failure(self):
        for response in [[],{"answers":None},{"answers":{"action":None}},{"answers":{"action":[]}}]:
            with self.subTest(response=response),patch.dict("os.environ",{"OPENROUTER_API_KEY":"unit-test-placeholder"},clear=True),patch("urllib.request.urlopen",return_value=io.BytesIO(json.dumps(response).encode())) as call:
                with self.assertRaises(ServiceFailure) as caught:
                    JevClient(config()).decide(make_request({},config()))
                self.assertEqual(call.call_count,1)
                self.assertIn("invalid_response",str(caught.exception))

    def test_transient_failure_retries_are_bounded(self):
        cfg = config()
        for status in [429,524]:
            with self.subTest(status=status):
                error = urllib.error.HTTPError("https://openrouter.ai/api/alpha/decisions",status,"transient",{},None)
                with patch.dict("os.environ",{"OPENROUTER_API_KEY":"unit-test-placeholder"},clear=True),patch("urllib.request.urlopen",side_effect=error) as call,patch("jev.time.sleep"):
                    with self.assertRaises(ServiceFailure) as caught:
                        JevClient(cfg).decide(make_request({},cfg))
                    self.assertEqual(call.call_count,cfg["api_retries"]+1)
                    self.assertEqual(caught.exception.attempts,cfg["api_retries"]+1)


if __name__ == "__main__":
    unittest.main()
