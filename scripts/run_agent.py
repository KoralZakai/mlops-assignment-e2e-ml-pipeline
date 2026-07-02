"""run_agent: run mini-swe-agent over the configured slice.

Reads runs/<run-id>/config.json and writes trajectories + preds.json into
runs/<run-id>/run-agent/. Usage: python scripts/run_agent.py runs/<run-id>
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def main(run_dir: str) -> None:
    run_dir = Path(run_dir)
    cfg = json.loads((run_dir / "config.json").read_text())
    agent_dir = run_dir / "run-agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "mini-extra", "swebench",
            "--subset", cfg["subset"],
            "--split", cfg["split"],
            "--model", cfg["model"],
            "--slice", cfg["task_slice"],
            "--workers", str(cfg["workers"]),
            # NB: batch `swebench` has no --cost-limit (only swebench-single does).
            # cost_limit is still recorded in config.json for provenance.
            "-o", str(agent_dir),
        ],
        env={**os.environ, "MSWEA_COST_TRACKING": "ignore_errors"},
        check=True,
    )


if __name__ == "__main__":
    main(sys.argv[1])
