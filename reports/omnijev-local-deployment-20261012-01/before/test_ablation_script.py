"""Exercise batch dispatch using an external-command stand-in, never an API."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parent/"scripts/run_model_ablation.sh"


class AblationScriptTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(),"nine-condition batch script is missing")
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"module"; (self.root/"scripts").mkdir(parents=True)
        self.script=self.root/"scripts/run_model_ablation.sh"
        shutil.copy2(SCRIPT,self.script)
        (self.root/"run.py").write_text("# not executed\n")
        (self.root/"config.single-gpu.json").write_text("{}")
        for name in ["debug-10.json","challenge-clearance-aligned-20260930-01/tasks.json",
                     "extended-clearance-aligned-20261008-01/tasks.json"]:
            p=self.root/"tasks"/name; p.parent.mkdir(parents=True,exist_ok=True);p.write_text("{}")
        fake=self.root/"fake-python"
        fake.write_text('#!/usr/bin/env python3\nimport json,os,sys\nwith open(os.environ["FAKE_CALLS"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n')
        fake.chmod(0o755)
        self.calls=self.root/"calls.jsonl"
        self.env={**os.environ,"NAV_PYTHON":str(fake),"FAKE_CALLS":str(self.calls),
                  "OPENROUTER_API_KEY":"unused-test-placeholder","CUDA_VISIBLE_DEVICES":"7"}
        for key in ["NAV_CONFIG","NAV_RGB","ROUTES","MODES"]: self.env.pop(key,None)

    def run_script(self,*args):
        return subprocess.run(["bash",str(self.script),*args],cwd=self.tmp.name,env=self.env,
                              text=True,capture_output=True,timeout=15)

    def test_dry_run_prints_nine_commands_without_key_or_execution(self):
        self.env.pop("OPENROUTER_API_KEY")
        result=self.run_script("openai","test-batch","--dry-run")
        self.assertEqual(result.returncode,0,result.stderr)
        commands=[shlex.split(l) for l in result.stdout.splitlines() if l.startswith("CUDA_VISIBLE_DEVICES=")]
        self.assertEqual(len(commands),9)
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.root/"runs").exists())

    def test_execute_dispatches_each_route_and_input_with_correct_budget_and_model(self):
        for model,prefix in [("openai","openai-decisions"),("jev","jev")]:
            with self.subTest(model=model):
                if self.calls.exists():self.calls.unlink()
                result=self.run_script(model,"test-batch")
                self.assertEqual(result.returncode,0,result.stderr)
                calls=[json.loads(l) for l in self.calls.read_text().splitlines()]
                self.assertEqual(len(calls),9)
                expected_routes={"simple":("tasks/debug-10.json","episode-000","100"),
                    "complex":("tasks/challenge-clearance-aligned-20260930-01/tasks.json","turn-000","250"),
                    "extended":("tasks/extended-clearance-aligned-20261008-01/tasks.json","extended-000","500")}
                seen=set()
                for args in calls:
                    flags=dict(zip(args[4::2],args[5::2])) # run.py --config FILE run FLAGS...
                    self.assertEqual(flags["--decision-model"],model)
                    for route,(task,episode,budget) in expected_routes.items():
                        if flags["--tasks"]==task:break
                    else:self.fail("unknown task dispatched")
                    mode="none" if flags["--depth-input"]=="none" else flags["--depth-format"]
                    self.assertEqual(flags["--episode"],episode)
                    self.assertEqual(flags["--max-steps"],budget)
                    self.assertEqual(flags["--out"],f"runs/{prefix}-{route}-rgbgs-{mode}-test-batch")
                    self.assertEqual(flags["--depth-format"],"semantic" if mode=="semantic" else "numeric")
                    seen.add((route,mode))
                self.assertEqual(seen,{(r,m) for r in expected_routes for m in ["numeric","semantic","none"]})

    def test_existing_later_output_prevents_all_dispatch_and_overwrite(self):
        old=self.root/"runs/openai-decisions-simple-rgbgs-semantic-test-batch"
        old.mkdir(parents=True);(old/"keep").write_text("original")
        result=self.run_script("openai","test-batch")
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(self.calls.exists())
        self.assertEqual((old/"keep").read_text(),"original")

    def test_missing_key_prevents_dispatch(self):
        self.env.pop("OPENROUTER_API_KEY")
        result=self.run_script("openai","test-batch")
        self.assertNotEqual(result.returncode,0)
        self.assertIn("OPENROUTER_API_KEY",result.stderr)
        self.assertFalse(self.calls.exists())

    def test_rgb_target_batch_passes_input_flag_and_uses_distinct_output_names(self):
        self.env['NAV_RGB_INPUT'] = 'target_marked'
        result = self.run_script('openai', 'rgb-batch')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(l) for l in self.calls.read_text().splitlines()]
        self.assertEqual(len(calls), 9)
        for args in calls:
            flags = dict(zip(args[4::2], args[5::2]))
            self.assertEqual(flags.get('--rgb-input'), 'target_marked')
            self.assertTrue(flags['--out'].startswith('runs/openai-decisions-rgbtarget-'))

    def test_rgb_target_batch_rejects_jev_or_missing_rgb_before_dispatch(self):
        self.env['NAV_RGB_INPUT'] = 'target_marked'
        for model, renderer in [('jev', 'gs'), ('openai', 'none')]:
            self.env['NAV_RGB'] = renderer
            result = self.run_script(model, 'invalid-rgb')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.calls.exists())

    def test_onejev_rgb_dry_run_and_dispatch_require_no_cloud_key(self):
        self.env.pop('OPENROUTER_API_KEY',None)
        self.env['NAV_RGB_INPUT']='target_marked'
        self.env['ONEJEV_BASE_URL']='http://127.0.0.1:9011'
        dry=self.run_script('onejev','local-test','--dry-run')
        self.assertEqual(dry.returncode,0,dry.stderr)
        self.assertEqual(len(dry.stdout.splitlines()),9)
        self.assertFalse(self.calls.exists())
        live=self.run_script('onejev','local-test')
        self.assertEqual(live.returncode,0,live.stderr)
        calls=[json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(len(calls),9)
        for argv in calls:
            flags=dict(zip(argv[4::2],argv[5::2]))
            self.assertEqual(flags['--decision-model'],'onejev')
            self.assertEqual(flags['--rgb-input'],'target_marked')
            self.assertEqual(flags['--onejev-url'],'http://127.0.0.1:9011')
            self.assertTrue(flags['--out'].startswith('runs/onejev-local-rgbtarget-'))

    def test_onejev_requires_explicit_render_gpu_but_legacy_defaults_survive(self):
        self.env.pop('CUDA_VISIBLE_DEVICES',None)
        result=self.run_script('onejev','missing-gpu','--dry-run')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('CUDA_VISIBLE_DEVICES',result.stderr)
        legacy=self.run_script('openai','legacy-gpu','--dry-run')
        self.assertEqual(legacy.returncode,0,legacy.stderr)


if __name__ == "__main__":unittest.main()
