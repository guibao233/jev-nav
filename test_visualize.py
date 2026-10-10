"""Offline bundle contracts; no network, simulator, or model credentials."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest

from PIL import Image

from visualize import build_viewer, default_output


class VisualizeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root/"run"
        (self.run/"frames").mkdir(parents=True)
        metadata = {"provider":"jev","rgb_mode":"gs",
            "map":{"origin_x":0,"origin_z":0,"resolution_m":.05,"width":100,"height":100},
            "task":{"start":[1,0,3],"goal":[1,0,1],"path":[[1,0,3],[1,0,1]]}}
        record = {"step":0,"frame_kind":"before_action","pose":{"position":[1,0,3],"yaw_rad":0},
            "images":{"rgb":"frames/rgb.png","depth":"frames/depth.png"},
            "request":{"state":{"task":{"step":1},"reference":{
                "current_target":{"forward_m":.75,"left_m":0,"distance_m":.75},
                "ordered_preview":[{"forward_m":.5,"left_m":0}]}}},
            "decision":None,"outcome":None,"metrics":{}}
        (self.run/"metadata.json").write_text(json.dumps(metadata))
        (self.run/"summary.json").write_text(json.dumps({"status":"action_budget"}))
        (self.run/"steps.jsonl").write_text(json.dumps(record)+"\n")
        for name in ["navmap.png","frames/rgb.png","frames/depth.png"]:
            Image.new("RGB",(100,100),"gray").save(self.run/name)
        self.request = record["request"]

    def test_portable_bundle_preserves_request_and_sources(self):
        before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.rglob('*') if p.is_file()}
        out = build_viewer(self.run,self.root/"viewer")
        html = (out/"index.html").read_text()
        payload = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S).group(1))
        r = payload["records"][0]
        self.assertEqual(r["request"],self.request)
        for name in [*r["images"].values(),r["map_image"]]:
            self.assertTrue((out/name).is_file())
            self.assertFalse(Path(name).is_absolute())
        self.assertTrue(json.loads((out/"visualization.json").read_text())["portable"])
        for path,digest in before.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)

    def test_missing_frame_fails_before_creating_output(self):
        (self.run/"frames/depth.png").unlink()
        out = self.root/"viewer"
        with self.assertRaisesRegex(ValueError,"缺少回放文件"):
            build_viewer(self.run,out)
        self.assertFalse(out.exists())

    def test_existing_output_is_never_overwritten(self):
        out = self.root/"viewer"
        out.mkdir()
        (out/"keep").write_text("existing")
        with self.assertRaises(FileExistsError):
            build_viewer(self.run,out)
        self.assertEqual((out/"keep").read_text(),"existing")

    def test_no_observations_has_clear_error(self):
        (self.run/"steps.jsonl").write_text("")
        with self.assertRaisesRegex(ValueError,"没有保存观察帧"):
            build_viewer(self.run,self.root/"viewer")

    def test_default_output_skips_existing_timestamp(self):
        from unittest.mock import patch
        with patch("visualize.datetime") as clock:
            clock.now.return_value.strftime.return_value = "fixed"
            first = default_output(self.run)
            first.mkdir(parents=True)
            self.assertNotEqual(first,default_output(self.run))


if __name__ == "__main__":
    unittest.main()
