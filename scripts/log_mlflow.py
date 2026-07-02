"""Log one run's config + metrics + artifact refs to MLflow.

Called by the DAGs via the project venv (which has mlflow). Optional 2nd arg is the
artifact URI from upload_s3.py (an s3://... URI or "local").

Tracking server: set MLFLOW_TRACKING_URI (e.g. http://localhost:5000). Unset ->
mlflow writes a local ./mlruns store, still reproducible for the speedrun.

Usage: python scripts/log_mlflow.py runs/<run-id> [artifact_uri]
"""

import json
import sys
from pathlib import Path

import mlflow


def main(run_dir: str, artifact_uri: str = "local") -> None:
    run_dir = Path(run_dir)
    config = json.loads((run_dir / "config.json").read_text())
    metrics = json.loads((run_dir / "metrics.json").read_text())

    mlflow.set_experiment("swebench-evaluate-agent")
    with mlflow.start_run(run_name=config["run_id"]):
        mlflow.log_params(config)
        mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
        mlflow.log_param("artifact_uri", artifact_uri)
        mlflow.log_param("artifact_local_path", str(run_dir.resolve()))
        # small, always-present artifacts; the full run dir is on S3/local (see uri)
        for name in ("config.json", "metrics.json", "manifest.json"):
            f = run_dir / name
            if f.exists():
                mlflow.log_artifact(str(f))
    print(f"logged MLflow run {config['run_id']} (artifact_uri={artifact_uri})")


if __name__ == "__main__":
    main(*sys.argv[1:3])
