"""run_eval: evaluate preds.json with the SWE-bench harness.

Reads runs/<run-id>/config.json. Runs the harness with cwd=run-eval so its logs/ and
<model>.<run_id>.json summary land in runs/<run-id>/run-eval/.
Usage: python scripts/run_eval.py runs/<run-id>
"""

import json
import os
import sys
from pathlib import Path
import subprocess


def main(run_dir: str) -> None:
    run_dir = Path(run_dir)
    cfg = json.loads((run_dir / "config.json").read_text())
    preds = (run_dir / "run-agent" / "preds.json").resolve()
    eval_dir = run_dir / "run-eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "python", "-m", "swebench.harness.run_evaluation",
            "--dataset_name", cfg["dataset_name"],
            "--predictions_path", str(preds),
            "--max_workers", str(cfg["workers"]),
            "--run_id", cfg["run_id"],
        ],
        cwd=eval_dir,
        # PYTHONPATH="": use the project venv's pyarrow/datasets, not Airflow's
        env={**os.environ, "PYTHONPATH": ""},
        check=True,
    )


if __name__ == "__main__":
    main(sys.argv[1])
