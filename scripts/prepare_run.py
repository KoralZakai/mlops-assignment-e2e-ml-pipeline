"""prepare_run: turn params into runs/<run-id>/config.json and print the run_id.

Prints run_id as the LAST stdout line so Airflow's DockerOperator can push it to
XCom for downstream tasks. Also usable directly: `python scripts/prepare_run.py ...`.
"""

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

# subset keyword -> HuggingFace dataset the SWE-bench eval harness expects
DATASET_BY_SUBSET = {
    "verified": "princeton-nlp/SWE-bench_Verified",
    "lite": "princeton-nlp/SWE-bench_Lite",
    "full": "princeton-nlp/SWE-bench",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="")
    ap.add_argument("--split", required=True)
    ap.add_argument("--subset", required=True)
    ap.add_argument("--workers", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--task-slice", required=True)
    ap.add_argument("--cost-limit", required=True)
    ap.add_argument("--runs-dir", default="runs")
    a = ap.parse_args()

    run_id = a.run_id or (
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    config = {
        "run_id": run_id,
        "split": a.split,
        "subset": a.subset,
        "workers": int(a.workers),
        "model": a.model,
        "task_slice": a.task_slice,
        "cost_limit": a.cost_limit,
        "dataset_name": DATASET_BY_SUBSET.get(a.subset, a.subset),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    run_dir = Path(a.runs_dir) / run_id
    (run_dir / "run-agent").mkdir(parents=True, exist_ok=True)
    (run_dir / "run-eval").mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(json.dumps(config, indent=2))

    print(f"wrote {run_dir / 'config.json'}")
    print(run_id)  # last line -> XCom


if __name__ == "__main__":
    main()
