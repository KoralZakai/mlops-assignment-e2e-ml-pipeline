"""evaluate_agent (easy-mode): run-agent -> run-eval -> durable runs/<run-id>/ + MLflow.

Thin orchestrator: every step is a scripts/<step>.py called via `uv run` (project venv,
not Airflow's tool env). The same scripts back the DockerOperator DAG
(evaluate_agent_docker.py), so pipeline logic lives in exactly one place.
"""

import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.models.param import Param

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "MSWEA_COST_TRACKING": "ignore_errors"}


def _uv(args, capture=False) -> str:
    r = subprocess.run(["uv", "run", *args], cwd=PROJECT_ROOT, env=ENV,
                        check=True, text=True, capture_output=capture)
    return _last_line(r.stdout) if capture else ""


def _last_line(text: str) -> str:
    return [ln for ln in text.splitlines() if ln.strip()][-1].strip()


@dag(
    dag_id="evaluate_agent",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=2)},
    params={
        "split":      Param("test",                        type="string"),
        "subset":     Param("verified", type="string", enum=["verified", "lite", "full"]),
        "workers":    Param(5,                             type="integer", minimum=1),
        "model":      Param("nebius/moonshotai/Kimi-K2.6", type="string"),
        "task_slice": Param("0:3",                         type="string"),
        "run_id":     Param("",                            type="string"),
        "cost_limit": Param("0",                           type="string"),
    },
)
def evaluate_agent():

    @task
    def prepare_run(**context) -> str:
        p = context["params"]
        return _uv([
            "python", "scripts/prepare_run.py",
            "--run-id", p["run_id"], "--split", p["split"], "--subset", p["subset"],
            "--workers", str(p["workers"]), "--model", p["model"],
            "--task-slice", p["task_slice"], "--cost-limit", str(p["cost_limit"]),
        ], capture=True)

    # NB: don't name a task arg `run_id` — it's a reserved Airflow context key.
    @task(execution_timeout=timedelta(hours=3))
    def run_agent(rid: str) -> str:
        _uv(["python", "scripts/run_agent.py", f"runs/{rid}"])
        return rid

    @task(execution_timeout=timedelta(hours=3))
    def run_eval(rid: str) -> str:
        _uv(["python", "scripts/run_eval.py", f"runs/{rid}"])
        return rid

    @task
    def summarize(rid: str) -> str:
        _uv(["python", "scripts/summarize.py", f"runs/{rid}"])
        return rid

    @task
    def upload_artifacts(rid: str) -> str:
        uri = _uv(["python", "scripts/upload_s3.py", f"runs/{rid}"], capture=True)
        return f"{rid}|{uri}"

    @task
    def log_metrics(rid_uri: str) -> None:
        rid, uri = rid_uri.split("|", 1)
        _uv(["python", "scripts/log_mlflow.py", f"runs/{rid}", uri])

    rid = prepare_run()
    rid = run_agent(rid)
    rid = run_eval(rid)
    rid = summarize(rid)
    log_metrics(upload_artifacts(rid))


evaluate_agent()
