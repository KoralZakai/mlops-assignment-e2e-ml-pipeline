"""evaluate_agent_docker (production-style): same pipeline, each step isolated in the
project image via DockerOperator.

Every task runs `python scripts/<step>.py runs/<run-id>` inside the image built from
the repo Dockerfile (default tag: mlops-agent:latest). The host runs/ and mlruns/
dirs are bind-mounted so artifacts persist; /var/run/docker.sock is mounted so the
agent and SWE-bench harness can launch their per-instance containers (docker-out-of-
docker). run_id flows between steps via prepare_run's XCom (its last stdout line).

Prereqs on the VM:
  uv sync                              # refresh uv.lock with mlflow/boto3
  docker build -t mlops-agent .        # build the project image
  # Airflow needs the docker provider (see run-airflow-standalone.sh)

Config via env (read where Airflow runs):
  AGENT_IMAGE          image tag (default mlops-agent:latest)
  NEBIUS_API_KEY       forwarded to the agent (or mount ~/.config/mini-swe-agent)
  MLFLOW_TRACKING_URI  default file:/mlops-assignment/mlruns (a bind-mounted local store)
  S3_BUCKET/S3_PREFIX/S3_ENDPOINT_URL/AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY  optional S3
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.models.param import Param
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get("AGENT_IMAGE", "mlops-agent:latest")
CONTAINER_ROOT = "/mlops-assignment"  # WORKDIR in the Dockerfile

# Host dirs (Airflow standalone runs on the VM, so these are docker-host paths).
RUNS_HOST = PROJECT_ROOT / "runs"
MLRUNS_HOST = PROJECT_ROOT / "mlruns"
RUNS_HOST.mkdir(exist_ok=True)
MLRUNS_HOST.mkdir(exist_ok=True)

RID = "{{ ti.xcom_pull(task_ids='prepare_run') }}"

_mounts = [
    Mount(source=str(RUNS_HOST), target=f"{CONTAINER_ROOT}/runs", type="bind"),
    Mount(source=str(MLRUNS_HOST), target=f"{CONTAINER_ROOT}/mlruns", type="bind"),
    Mount(source="/var/run/docker.sock", target="/var/run/docker.sock", type="bind"),
]
# Reuse the working mini-swe-agent key file if present (else rely on NEBIUS_API_KEY env).
_mini_cfg = Path(os.path.expanduser("~/.config/mini-swe-agent"))
if _mini_cfg.is_dir():
    _mounts.append(Mount(source=str(_mini_cfg), target="/root/.config/mini-swe-agent",
                         type="bind", read_only=True))

_env = {
    "MSWEA_COST_TRACKING": "ignore_errors",
    # Inside a container 127.0.0.1 is the container itself; reach the host's MLflow
    # server via the docker host gateway (see extra_hosts below). Override with
    # MLFLOW_DOCKER_TRACKING_URI if MLflow runs elsewhere.
    "MLFLOW_TRACKING_URI": os.environ.get("MLFLOW_DOCKER_TRACKING_URI", "http://host.docker.internal:5000"),
}
for k in ("NEBIUS_API_KEY", "S3_BUCKET", "S3_PREFIX", "S3_ENDPOINT_URL",
          "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
    if os.environ.get(k):
        _env[k] = os.environ[k]


def step(task_id: str, command: list[str], timeout_h: int = 1) -> DockerOperator:
    return DockerOperator(
        task_id=task_id,
        image=IMAGE,
        command=command,
        mounts=_mounts,
        environment=_env,
        extra_hosts={"host.docker.internal": "host-gateway"},  # reach host MLflow
        docker_url="unix://var/run/docker.sock",
        network_mode="bridge",
        auto_remove="success",
        mount_tmp_dir=False,
        execution_timeout=timedelta(hours=timeout_h),
    )


with DAG(
    dag_id="evaluate_agent_docker",
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
) as dag:
    prepare_run = step("prepare_run", [
        "python", "scripts/prepare_run.py",
        "--run-id", "{{ params.run_id }}", "--split", "{{ params.split }}",
        "--subset", "{{ params.subset }}", "--workers", "{{ params.workers }}",
        "--model", "{{ params.model }}", "--task-slice", "{{ params.task_slice }}",
        "--cost-limit", "{{ params.cost_limit }}",
    ])
    run_agent = step("run_agent", ["python", "scripts/run_agent.py", f"runs/{RID}"], timeout_h=3)
    run_eval = step("run_eval", ["python", "scripts/run_eval.py", f"runs/{RID}"], timeout_h=3)
    summarize = step("summarize", ["python", "scripts/summarize.py", f"runs/{RID}"])
    upload_artifacts = step("upload_artifacts", ["python", "scripts/upload_s3.py", f"runs/{RID}"])
    log_metrics = step("log_metrics", [
        "python", "scripts/log_mlflow.py", f"runs/{RID}",
        "{{ ti.xcom_pull(task_ids='upload_artifacts') }}",
    ])

    prepare_run >> run_agent >> run_eval >> summarize >> upload_artifacts >> log_metrics
