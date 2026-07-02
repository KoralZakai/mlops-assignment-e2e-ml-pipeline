#!/usr/bin/env bash
# Start the MLflow tracking server on a SQLite backend (a supported DB store;
# the legacy ./mlruns file store is blocked by newer MLflow).
# UI + API on http://127.0.0.1:5000. Tunnel from your laptop:
#   ssh -N -L 5000:localhost:5000 koral@<vm>
set -euo pipefail
cd "$(dirname "$0")"

# --allowed-hosts '*': the DockerOperator tasks connect via host.docker.internal,
# which MLflow's anti-DNS-rebinding middleware blocks by default (localhost-only).
exec uv run mlflow server \
  --backend-store-uri "sqlite:///$PWD/mlflow.db" \
  --default-artifact-root "file:$PWD/mlartifacts" \
  --host 0.0.0.0 --port 5000 \
  --allowed-hosts '*' --cors-allowed-origins '*'
