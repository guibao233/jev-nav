"""Compare saved v5 requests with current request construction, without API/GPU."""
import argparse
import json
from pathlib import Path
import sys

MODULE = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(MODULE))
from jev import make_request

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--runs-root",type=Path,default=MODULE)
args=parser.parse_args()
rows=json.loads((args.runs_root/"reports/route-ablation-summary-20261008-01/summary.json").read_text())["rows"]
count=0
for row in rows:
    folder=args.runs_root/"runs"/row["run"]
    cfg=json.loads((folder/"metadata.json").read_text())["config"]
    for line in (folder/"steps.jsonl").read_text().splitlines():
        record=json.loads(line)
        if not record.get("outcome"):
            continue
        saved=record["request"]
        state=dict(saved["state"])
        if cfg.get("depth_format")=="semantic" and cfg.get("depth_input","mesh")!="none":
            state["depth"]=record["depth_numeric_debug"]
        assert make_request(state,cfg)==saved,(row["run"],record["step"])
        alternate=make_request(state,dict(cfg,model="openai/gpt-6-luna-decisions"))
        assert alternate["model"]=="openai/gpt-6-luna-decisions"
        assert {k:v for k,v in alternate.items() if k!="model"}=={k:v for k,v in saved.items() if k!="model"}
        count+=1
print(json.dumps({"runs":len(rows),"requests":count,"default_jev_requests_unchanged":True,
                  "openai_requests_differ_only_in_model":True,"api_calls":0,"used_gpu":False},indent=2))
