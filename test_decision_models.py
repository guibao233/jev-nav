"""Model selection and saved evaluation identity; no real API or renderer."""
import argparse
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from jev import JevClient, make_request
from run import main, run_episode
from test_core import config
from test_semantic_depth import numeric_facts

OPENAI_MODEL = "openai/gpt-6-luna-decisions"
ROOT = Path(__file__).resolve().parent


def response(model, action):
    return {"id":"test-only", "model":model,
            "provider":"OpenAI" if model == OPENAI_MODEL else "TypeSafe",
            "answers":{"action":{"type":"choice", "choice":action,
                "probabilities":{action:1.0}, "confidence":1.0}},
            "usage":{"input_tokens":100, "output_tokens":0, "cost":0.00001}}


class ModelSwitchTests(unittest.TestCase):
    def test_openai_cli_missing_key_fails_before_loading_tasks_or_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"must-not-exist"
            env={k:v for k,v in os.environ.items() if k != "OPENROUTER_API_KEY"}
            result=subprocess.run([sys.executable,"-B",str(ROOT/"run.py"),"run",
                "--decision-model","openai","--tasks",str(Path(tmp)/"missing.json"),
                "--out",str(out),"--rgb","none"],env=env,text=True,capture_output=True,timeout=15)
            self.assertNotEqual(result.returncode,0)
            self.assertIn("OPENROUTER_API_KEY",result.stderr)
            self.assertFalse(out.exists())

    def test_unknown_model_is_not_silently_reported_as_jev(self):
        with patch.dict("os.environ",{"OPENROUTER_API_KEY":"test-placeholder"},clear=True):
            with self.assertRaisesRegex(ValueError,"unsupported decision model"):
                JevClient(dict(config(),model="unknown/model"))

    def test_cli_selects_model_and_default_preserves_jev(self):
        for command in ["run", "smoke"]:
            for flags, expected in [([], "typesafe/jev-1.13"),
                                    (["--decision-model","openai"], OPENAI_MODEL),
                                    (["--decision-model","jev"], "typesafe/jev-1.13")]:
                argv = ["run.py", command, "--tasks", "same.json", "--out", "unused", *flags]
                with self.subTest(command=command, flags=flags), patch("sys.argv",argv), patch("run.run_episode",return_value=0) as runner:
                    try:
                        self.assertEqual(main(),0)
                    except SystemExit:
                        self.fail("run/smoke must accept --decision-model")
                    args, cfg = runner.call_args.args
                    self.assertEqual(cfg["model"],expected)
                    self.assertEqual(args.tasks,"same.json")

    def test_switch_changes_only_model_in_all_three_input_conditions(self):
        original = {"depth":numeric_facts(), "reference":{"current_target":{"is_final":False}},
                    "recent_actions":[]}
        saved = copy.deepcopy(original)
        for depth_input, depth_format in [("mesh","numeric"),("mesh","semantic"),("none","numeric")]:
            cfg = dict(config(),depth_input=depth_input,depth_format=depth_format)
            baseline = make_request(original,cfg)
            alternate = make_request(original,dict(cfg,model=OPENAI_MODEL))
            self.assertEqual(alternate.pop("model"),OPENAI_MODEL)
            baseline.pop("model")
            self.assertEqual(alternate,baseline)
        self.assertEqual(original,saved)

    def test_openai_transport_preserves_protocol_and_reports_correct_identity(self):
        cfg = dict(config(),model=OPENAI_MODEL)
        payload = make_request({"recent_actions":[]},cfg)
        fixture = response(OPENAI_MODEL,"move_backward")
        with patch.dict("os.environ",{"OPENROUTER_API_KEY":"test-placeholder"},clear=True), patch("urllib.request.urlopen",return_value=io.BytesIO(json.dumps(fixture).encode())) as transport:
            result = JevClient(cfg).decide(payload)
        self.assertEqual(result["provider"],"openai_decisions")
        self.assertEqual(result["choice"],"move_backward")
        self.assertEqual(result["response"],fixture)
        sent = transport.call_args.args[0]
        self.assertEqual(sent.full_url,"https://openrouter.ai/api/alpha/decisions")
        self.assertEqual(json.loads(sent.data),payload)
        self.assertNotIn("test-placeholder",json.dumps(result))


class FlatPathfinder:
    def is_navigable(self,point): return True
    def try_step(self,start,end): return np.asarray(end)
    def get_topdown_view(self,resolution,height): return np.ones((60,60),dtype=bool)
    def get_bounds(self): return np.array([0,0,0]),np.array([3,1,3])


class ScriptedEnvironment:
    """Only replace the GPU boundary; runner, transport, files and replay are real."""
    def __init__(self,cfg,output,rgb): self.pitch=0; self.position=None
    def reset(self,task): self.position=np.asarray(task["start"],dtype=float)
    def pose(self): return self.position.copy(),0.0
    def observe(self): return np.full((24,32),3.0),None
    def act(self,action):
        moved = .25 if action == "move_forward" else 0.0
        self.position[2] -= moved
        return {"action":action,"valid":True,"success":True,"collided":False,
                "actual_translation_m":moved,"actual_forward_m":moved,"actual_left_m":0.,
                "actual_yaw_deg":0.,"actual_pitch_deg":0.,"result":"executed"}
    def close(self): pass


class SavedIdentityTests(unittest.TestCase):
    def test_live_and_smoke_outputs_distinguish_models_and_keep_navigation_metrics(self):
        for model, family, label in [("typesafe/jev-1.13","jev","Jev"),
                                     (OPENAI_MODEL,"openai_decisions","GPT-6 Luna Decisions")]:
            for live in [True,False]:
                with self.subTest(model=model,live=live), tempfile.TemporaryDirectory() as tmp:
                    root=Path(tmp); tasks=root/"tasks.json"; out=root/"run"
                    task={"id":"test","start":[1,0,2],"goal":[1,0,1.75],
                          "path":[[1,0,2],[1,0,1.75]],"geodesic_m":.25,"yaw_deg":0,"pitch_deg":0}
                    tasks.write_text(json.dumps({"tasks":[task]}))
                    args=argparse.Namespace(command="run" if live else "smoke",tasks=str(tasks),
                        episode="test",out=str(out),rgb="none",actions="move_forward,stop")
                    cfg=dict(config(),model=model,max_steps=2,depth_input="none")
                    responses=[io.BytesIO(json.dumps(response(model,a)).encode()) for a in ["move_forward","stop"]]
                    def flat_shortest(pf,start,goal):
                        return float(np.linalg.norm(np.asarray(goal)-np.asarray(start))),[start,goal]
                    with patch.dict("os.environ",{"OPENROUTER_API_KEY":"test-placeholder"},clear=True), patch("run.asset_manifest",return_value={}), patch("run.load_pathfinder",return_value=FlatPathfinder()), patch("run.shortest",side_effect=flat_shortest), patch("run.Environment",ScriptedEnvironment), patch("urllib.request.urlopen",side_effect=responses) as transport, contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(run_episode(args,cfg),0)
                    summary=json.loads((out/"summary.json").read_text())
                    metadata=json.loads((out/"metadata.json").read_text())
                    for data in [summary,metadata]:
                        self.assertEqual(data["provider"],family if live else "scripted_smoke")
                        self.assertEqual(data.get("requested_model"),model)
                        self.assertEqual(data.get("model_label"),label)
                        self.assertEqual(data.get("is_model_evaluation"),live)
                        self.assertEqual(data.get("is_jev_evaluation"),live and family=="jev")
                        self.assertEqual(data.get("is_openai_decisions_evaluation"),live and family=="openai_decisions")
                    self.assertEqual(summary["response_models"],[model] if live else [])
                    self.assertEqual(summary["steps"],2)
                    self.assertTrue(summary["success"])
                    self.assertEqual(summary["path_length_m"],.25)
                    self.assertEqual(summary["final_geodesic_m"],0.)
                    self.assertEqual(transport.call_count,2 if live else 0)
                    if live:
                        self.assertIsNotNone(summary["model_request_latency"])
                    else:
                        self.assertIsNone(summary["model_request_latency"])
                    if family != "jev" or not live:
                        self.assertIsNone(summary["jev_request_latency"])
                    html=(out/"index.html").read_text()
                    self.assertIn(f"<title>{label} 路径跟随实验回放</title>",html)


if __name__ == "__main__": unittest.main()
