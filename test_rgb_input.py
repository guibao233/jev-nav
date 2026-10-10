"""Projection and real request/log boundaries; no GPU or paid requests."""
import argparse
import base64
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
try:
    import rgb_input
except ModuleNotFoundError:
    rgb_input = None
from core import RoutePreview
from jev import DecisionsClient, make_request
from run import main, run_episode
from test_core import config
from test_decision_models import FlatPathfinder, ScriptedEnvironment, response
from test_semantic_depth import numeric_facts

MODEL = 'openai/gpt-6-luna-decisions'


class RgbEnvironment(ScriptedEnvironment):
    def observe(self):
        return np.full((480, 640), 3., np.float32), np.full((480, 640, 3), 80, np.uint8)


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(rgb_input, 'RGB target annotation feature is missing')
        self.cfg = dict(config(), model=MODEL, rgb_input='target_marked')

    def target(self, forward=3., left=0.):
        return {'forward_m': forward, 'left_m': left, 'distance_m': 3., 'bearing_deg': 0., 'is_final': False}

    def test_center_and_left_target_follow_pinhole_geometry(self):
        center = rgb_input.project_target(self.target(), 0, self.cfg)
        self.assertEqual(center['projection_status'], 'in_frame')
        np.testing.assert_allclose(center['pixel_xy'], [319.5, 399.5], atol=1e-5)
        left = rgb_input.project_target(self.target(left=.75), 0, self.cfg)
        np.testing.assert_allclose(left['pixel_xy'], [239.5, 399.5], atol=1e-5)

    def test_near_ground_target_is_outside_frame_until_camera_looks_down(self):
        target = self.target(forward=.75)
        level = rgb_input.project_target(target, 0, self.cfg)
        self.assertEqual(level['projection_status'], 'outside_frame')
        self.assertGreater(level['pixel_xy'][1], 480)
        down = rgb_input.project_target(target, 45, self.cfg)
        self.assertEqual(down['projection_status'], 'in_frame')
        np.testing.assert_allclose(down['pixel_xy'], [319.5, 346.1666667], atol=1e-5)

    def test_behind_camera_is_not_fabricated_as_a_visible_target(self):
        info = rgb_input.project_target(self.target(forward=-3.), 0, self.cfg)
        self.assertEqual(info['projection_status'], 'behind_camera')
        self.assertIsNone(info['pixel_xy'])

    def test_height_difference_and_route_target_are_retained(self):
        info = rgb_input.project_target(self.target(), 0, self.cfg, target_height_m=1.5)
        np.testing.assert_allclose(info['pixel_xy'], [319.5, 239.5], atol=1e-5)
        route = RoutePreview([[0, 0, 0], [0, 1, -3]])
        route.state([0, 0, 0], 0, self.cfg)
        self.assertGreater(route.current_target_point[1], 0)

    def test_marker_changes_copy_only_and_arrow_is_distinct(self):
        pixels = np.full((480, 640, 3), 80, np.uint8)
        original = pixels.copy()
        visible, a = rgb_input.annotate_target(pixels, self.target(), 0, self.cfg)
        outside, b = rgb_input.annotate_target(pixels, self.target(forward=.75), 0, self.cfg)
        self.assertEqual(a['marker_kind'], 'projected_point')
        self.assertEqual(b['marker_kind'], 'offscreen_arrow')
        np.testing.assert_array_equal(pixels, original)
        self.assertFalse(np.array_equal(np.asarray(visible), original))
        self.assertFalse(np.array_equal(np.asarray(outside), original))

    def test_upward_offscreen_arrow_is_not_hidden_by_the_caption(self):
        _, info = rgb_input.annotate_target(np.zeros((480, 640, 3), np.uint8),
            self.target(forward=20.), 45, self.cfg)
        self.assertEqual(info['marker_kind'], 'offscreen_arrow')
        self.assertGreater(info['marker_pixel_xy'][1], 37)

    def test_target_at_feet_is_not_mislabelled_as_behind_camera(self):
        info = rgb_input.project_target(self.target(forward=0.), 0, self.cfg)
        self.assertEqual(info['projection_status'], 'camera_plane')

    def test_visible_marker_takes_priority_over_caption_background(self):
        image, info = rgb_input.annotate_target(np.zeros((480, 640, 3), np.uint8),
            self.target(), 0, self.cfg, target_height_m=3.45)
        self.assertEqual(info['projection_status'], 'in_frame')
        self.assertTrue(np.any(np.all(np.asarray(image)[25:38, 315:325] == [255, 70, 215], axis=-1)))


class RgbRequestTests(unittest.TestCase):
    def test_rgb_transport_keeps_each_depth_ablation_condition(self):
        for mode, representation in [('mesh', 'numeric'), ('mesh', 'semantic'), ('none', 'numeric')]:
            cfg = dict(config(), model=MODEL, rgb_input='target_marked', depth_input=mode, depth_format=representation)
            state = {'depth': numeric_facts(), 'recent_actions': []}
            original = copy.deepcopy(state)
            payload = make_request(state, cfg)
            with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-placeholder'}, clear=True), patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response(MODEL, 'stop')).encode())) as transport:
                DecisionsClient(cfg).decide(payload, image_bytes=b'only-a-transport-fixture')
            sent = json.loads(transport.call_args.args[0].data)
            text_state = json.loads(sent['state'][0])
            if mode == 'none':
                self.assertNotIn('depth', text_state)
            elif representation == 'semantic':
                self.assertEqual(text_state['depth']['format'], 'semantic')
                self.assertNotIn('nearest_obstacle_m', json.dumps(text_state['depth']))
            else:
                self.assertIn('nearest_obstacle_m', text_state['depth']['sectors'][0])
            self.assertEqual(state, original)
    def test_cli_accepts_rgb_input_without_changing_model_or_depth(self):
        with patch('sys.argv', ['run.py', 'run', '--tasks', 'unused', '--out', 'unused', '--decision-model', 'openai', '--rgb-input', 'target_marked']), patch('run.run_episode', return_value=0) as runner:
            try:
                self.assertEqual(main(), 0)
            except SystemExit:
                self.fail('CLI must accept --rgb-input target_marked')
            self.assertEqual(runner.call_args.args[1]['rgb_input'], 'target_marked')
            self.assertEqual(runner.call_args.args[1]['model'], MODEL)

    def test_invalid_combinations_fail_before_any_output_or_api_initialization(self):
        for model, renderer in [('typesafe/jev-1.13', 'gs'), (MODEL, 'none')]:
            cfg = dict(config(), model=model, rgb_input='target_marked')
            args = argparse.Namespace(command='run', rgb=renderer, tasks='missing', episode='missing', out='unused')
            with self.subTest(model=model, renderer=renderer), patch('run.DecisionsClient') as client:
                with self.assertRaisesRegex(ValueError, 'RGB input'):
                    run_episode(args, cfg)
                client.assert_not_called()

    def test_no_depth_rgb_prompt_does_not_claim_camera_observations_are_absent(self):
        payload = make_request({'depth': {'private': 'must be absent'}, 'recent_actions': []}, dict(config(), model=MODEL, depth_input='none', rgb_input='target_marked'))
        self.assertNotIn('depth', payload['state'])
        text = payload['questions']['action']['instructions']
        self.assertNotIn('No depth or image observations', text)
        self.assertNotIn('Camera tilts do not reveal', text)
        self.assertIn('RGB', text)

    def test_enabled_mode_cannot_silently_send_text_only(self):
        cfg = dict(config(), model=MODEL, rgb_input='target_marked')
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-placeholder'}, clear=True), patch('urllib.request.urlopen') as transport:
            client = DecisionsClient(cfg)
            with self.assertRaisesRegex(ValueError, 'image'):
                client.decide(make_request({'recent_actions': []}, cfg))
            transport.assert_not_called()

    def test_runner_sends_exact_saved_image_and_retains_readable_log_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root/'run'; tasks = root/'tasks.json'
            tasks.write_text(json.dumps({'tasks': [{'id': 'test', 'start': [1, 0, 2], 'goal': [1, 0, 1.75], 'path': [[1, 0, 2], [1, 0, 1.75]], 'geodesic_m': .25, 'yaw_deg': 0, 'pitch_deg': 0}]}))
            args = argparse.Namespace(command='run', tasks=str(tasks), episode='test', out=str(out), rgb='gs')
            cfg = dict(config(), model=MODEL, rgb_input='target_marked', depth_input='none', max_steps=2)
            wire = []
            def http(req, timeout):
                wire.append(req.data)
                return io.BytesIO(json.dumps(response(MODEL, ['move_forward', 'stop'][len(wire)-1])).encode())
            def shortest(pf, start, goal):
                return float(np.linalg.norm(np.asarray(goal)-np.asarray(start))), [start, goal]
            with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-placeholder'}, clear=True), patch('run.asset_manifest', return_value={}), patch('run.load_pathfinder', return_value=FlatPathfinder()), patch('run.shortest', side_effect=shortest), patch('run.Environment', RgbEnvironment), patch('urllib.request.urlopen', side_effect=http), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_episode(args, cfg), 0)
            records = [json.loads(l) for l in (out/'steps.jsonl').read_text().splitlines()]
            for record, body in zip(records, wire):
                sent = json.loads(body); self.assertEqual(sent['model'], MODEL)
                self.assertIsInstance(sent['state'][0], str)
                self.assertEqual(json.loads(sent['state'][0]), record['request']['state'])
                self.assertNotIn('depth', json.loads(sent['state'][0]))
                part = sent['state'][1]; self.assertEqual(part['type'], 'image_url')
                mime, encoded = part['image_url']['url'].split(',', 1)
                self.assertEqual(mime, 'data:image/jpeg;base64')
                saved = (out/record['image_input']['path']).read_bytes()
                self.assertEqual(base64.b64decode(encoded), saved)
                self.assertEqual(hashlib.sha256(saved).hexdigest(), record['image_input']['sha256'])
                self.assertEqual(hashlib.sha256(body).hexdigest(), record['wire_request_sha256'])
            self.assertNotIn('base64,', (out/'steps.jsonl').read_text())
            for filename in ['metadata.json', 'summary.json']:
                data = json.loads((out/filename).read_text()); self.assertTrue(data['rgb_provided_to_model'])
                self.assertEqual(data['rgb_input'], 'target_marked')
            self.assertTrue(json.loads((out/'summary.json').read_text())['success'])
            self.assertIn(records[0]['image_input']['path'], (out/'index.html').read_text())
            self.assertIn('modelRgb', (out/'index.html').read_text())
            from visualize import build_viewer
            with contextlib.redirect_stdout(io.StringIO()):
                viewer = build_viewer(out, root/'portable')
            copied = viewer/'observations/00000-model_rgb.jpg'
            self.assertTrue(copied.is_file(), 'portable replay must include the actual model image')
            self.assertEqual(copied.read_bytes(), (out/records[0]['image_input']['path']).read_bytes())

    def test_smoke_prepares_images_without_claiming_a_live_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root/'run'; tasks = root/'tasks.json'
            tasks.write_text(json.dumps({'tasks': [{'id': 'test', 'start': [1, 0, 2], 'goal': [1, 0, 1.75], 'path': [[1, 0, 2], [1, 0, 1.75]], 'geodesic_m': .25, 'yaw_deg': 0, 'pitch_deg': 0}]}))
            args = argparse.Namespace(command='smoke', tasks=str(tasks), episode='test', out=str(out), rgb='gs', actions='move_forward,stop')
            cfg = dict(config(), model=MODEL, rgb_input='target_marked', depth_input='none', max_steps=2)
            with patch.dict(os.environ, {}, clear=True), patch('run.asset_manifest', return_value={}), patch('run.load_pathfinder', return_value=FlatPathfinder()), patch('run.shortest', side_effect=lambda pf, a, b: (float(np.linalg.norm(np.asarray(b)-np.asarray(a))), [a,b])), patch('run.Environment', RgbEnvironment), patch('urllib.request.urlopen') as transport, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_episode(args, cfg), 0)
            transport.assert_not_called()
            for filename in ['metadata.json', 'summary.json']:
                data = json.loads((out/filename).read_text())
                self.assertFalse(data['rgb_provided_to_model'])
                self.assertFalse(data['is_model_evaluation'])
            self.assertTrue((out/'frames/00000-model-rgb.jpg').exists())


if __name__ == '__main__': unittest.main()
