"""summarize: parse the SWE-bench report into metrics.json and write manifest.json.

Makes runs/<run-id>/ self-describing (Phase 2): a teammate can grab the folder and
see where predictions, trajectories, eval logs, report, and metrics live.

Usage: python scripts/summarize.py runs/<run-id>
"""

import json
import sys
from pathlib import Path


def collect_metrics(eval_dir: Path) -> dict:
    """The harness writes one <model>.<run_id>.json summary at the eval dir root."""
    reports = [p for p in eval_dir.glob("*.json")]
    if not reports:
        raise FileNotFoundError(f"No SWE-bench summary report in {eval_dir}")
    report = json.loads(reports[0].read_text())
    submitted = report.get("submitted_instances", 0)
    resolved = report.get("resolved_instances", 0)
    return {
        "submitted": submitted,
        "resolved": resolved,
        "completed": report.get("completed_instances", 0),
        "unresolved": report.get("unresolved_instances", 0),
        "errors": report.get("error_instances", 0),
        "empty_patches": report.get("empty_patch_instances", 0),
        # ponytail: guard div0 when a run submitted nothing
        "resolve_rate": resolved / submitted if submitted else 0.0,
    }


def build_manifest(run_dir: Path, metrics: dict) -> dict:
    eval_dir = run_dir / "run-eval"
    summary = next((p.name for p in eval_dir.glob("*.json")), None)

    def rel(p: Path) -> str | None:
        return p.relative_to(run_dir).as_posix() if p.exists() else None

    return {
        "run_id": run_dir.name,
        "config": rel(run_dir / "config.json"),
        "predictions": rel(run_dir / "run-agent" / "preds.json"),
        "trajectories": rel(run_dir / "run-agent"),
        "eval_logs": rel(eval_dir / "logs"),
        "eval_report": f"run-eval/{summary}" if summary else None,
        "metrics": rel(run_dir / "metrics.json"),
        "resolve_rate": metrics["resolve_rate"],
        # where the full artifacts live; s3 filled in by upload_s3.py -> MLflow
        "artifact_location": {"local": str(run_dir.resolve()), "s3": None},
    }


def main(run_dir: str) -> None:
    run_dir = Path(run_dir)
    metrics = collect_metrics(run_dir / "run-eval")
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (run_dir / "manifest.json").write_text(json.dumps(build_manifest(run_dir, metrics), indent=2))
    print(f"metrics: {metrics}")


if __name__ == "__main__":
    main(sys.argv[1])
