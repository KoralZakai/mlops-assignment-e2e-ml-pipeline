# REPORT — Evaluation pipeline for coding-agent experiments

Turns the ad-hoc `scripts/` into a configurable, durable, tracked Airflow pipeline:
**run mini-swe-agent → evaluate with SWE-bench → write a reproducible run folder → log to MLflow**.

## Architecture

```
Airflow DAG (params) ──> prepare_run ─> run_agent ─> run_eval ─> summarize ─> upload_artifacts ─> log_metrics
                              │             │            │            │              │                 │
                         config.json   preds.json    eval logs    metrics.json    S3 (opt)          MLflow
                                       trajectories   + report     manifest.json                    (SQLite)
```

Two DAGs, one shared code path:

| DAG | Execution | Use |
|---|---|---|
| `dags/evaluate_agent.py` | each step via `uv run` in the project venv | easy-mode / default |
| `dags/evaluate_agent_docker.py` | each step via `DockerOperator` in the `mlops-agent` image (docker-out-of-docker) | production-style isolation |

All pipeline logic lives in `scripts/*.py` (single source of truth); both DAGs just call
`python scripts/<step>.py runs/<run-id>`. Each step reads `runs/<run-id>/config.json`, so
tasks are stateless and only pass the `run_id` between them.

- `scripts/prepare_run.py` — params → `runs/<run-id>/config.json`, prints `run_id`
- `scripts/run_agent.py` — `mini-extra swebench` → trajectories + `preds.json`
- `scripts/run_eval.py` — `swebench.harness.run_evaluation` → logs + summary report
- `scripts/summarize.py` — parse report → `metrics.json` + `manifest.json`
- `scripts/upload_s3.py` — tar + upload run dir to S3 (guarded; skipped if `S3_BUCKET` unset)
- `scripts/log_mlflow.py` — log params, metrics, artifact refs to MLflow

Retries (`retries=2`) and timeouts (3h on agent/eval) are set on both DAGs.

## Parameters (Airflow UI → Trigger DAG w/ config)

| Param | Default | Notes |
|---|---|---|
| `split` | `test` | SWE-bench split |
| `subset` | `verified` | `verified` / `lite` / `full` → HF dataset |
| `workers` | `5` | agent + eval parallelism |
| `model` | `nebius/moonshotai/Kimi-K2.6` | any litellm model id |
| `task_slice` | `0:3` | subset of instances, e.g. `0:1` for a smoke test |
| `run_id` | *(blank)* | blank → auto `YYYYMMDD_HHMMSS_<hex>` |
| `cost_limit` | `0` | recorded in config; enforced only in single-task mode |

No experiment values are hard-coded in the DAG.

## Artifact layout (durable, self-describing)

```
runs/<run-id>/
  config.json            # exact params + dataset + timestamp
  run-agent/
    preds.json           # SWE-bench predictions
    <instance>/…traj.json# agent trajectories
  run-eval/
    logs/run_evaluation/…# per-instance eval logs
    <model>.<run-id>.json# SWE-bench summary report
  metrics.json           # submitted/resolved/…/resolve_rate
  manifest.json          # pointers to all of the above + artifact_location (local + s3)
```

`manifest.json` makes the folder portable: hand someone `runs/<run-id>/` and they can
reconstruct inputs, outputs, logs, and metrics.

## MLflow tracking

MLflow runs as a SQLite-backed server (`run-mlflow.sh`, port 5000). Each pipeline run logs
params, metrics, and artifact references to the `swebench-evaluate-agent` experiment, so
multiple runs are directly comparable in the UI.

- Start: `bash run-mlflow.sh` (or `nohup bash run-mlflow.sh &`)
- Airflow forwards `MLFLOW_TRACKING_URI=http://127.0.0.1:5000` to tasks automatically.
- Screenshot: `screenshots/mlflow_runs.png`

> Note: newer MLflow blocks the legacy `./mlruns` file store; we use `sqlite:///mlflow.db`,
> the supported DB backend.

## A completed run (`test02`)

`subset=verified, split=test, task_slice=0:1, workers=1` →

```json
{ "submitted": 1, "resolved": 1, "completed": 1,
  "unresolved": 0, "errors": 0, "empty_patches": 0, "resolve_rate": 1.0 }
```

Full artifacts under `runs/test02/`; logged to MLflow experiment `swebench-evaluate-agent`.

## How to run

Setup (VM, once): `uv sync`, put `NEBIUS_API_KEY` in `~/.config/mini-swe-agent/.env`.

```bash
# terminal 1 (VM): MLflow
nohup bash run-mlflow.sh > ~/mlflow.log 2>&1 &

# terminal 2 (VM): Airflow
nohup bash run-airflow-standalone.sh > ~/airflow.log 2>&1 &

# laptop: tunnels
ssh -N -L 8080:localhost:8080 -L 5000:localhost:5000 koral@<vm>
```

- Airflow UI: http://localhost:8080 (admin/admin) → trigger `evaluate_agent`.
- MLflow UI: http://localhost:5000.

**Production-style (DockerOperator):**
```bash
docker build -t mlops-agent .          # build the project image
```
then trigger `evaluate_agent_docker` (mounts `runs/`, `mlruns/`, and `/var/run/docker.sock`).

## Rerun by run-id

Every run is fully described by `runs/<run-id>/config.json`. To reproduce, trigger the DAG
with the same params (or set `run_id` explicitly to overwrite/extend that folder). Re-logging
metrics without re-running the agent: `uv run python scripts/log_mlflow.py runs/<run-id> local`.

## Remote storage (S3 / Object Storage)

`upload_artifacts` tars `runs/<run-id>/` and uploads to any S3-compatible store when configured
(`S3_BUCKET`, `S3_ENDPOINT_URL`, `AWS_*`); the URI is logged to MLflow. Unset → the step no-ops
and the local `runs/<run-id>/` folder is the artifact. See `.env.example`.
