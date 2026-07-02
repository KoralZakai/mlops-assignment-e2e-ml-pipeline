set -euo pipefail

export AIRFLOW_HOME=~/airflow
export AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/dags
export AIRFLOW__CORE__LOAD_EXAMPLES=false

# Log pipeline runs to the SQLite-backed MLflow server (run-mlflow.sh).
# Tasks inherit this, so scripts/log_mlflow.py logs here instead of ./mlruns.
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000

mkdir -p $AIRFLOW_HOME

echo '{"admin": "admin"}' > $AIRFLOW_HOME/simple_auth_manager_passwords.json.generated

# --with apache-airflow-providers-docker: needed so evaluate_agent_docker.py
# (DockerOperator) can be imported by Airflow. Harmless for the other DAGs.
uv tool run --with apache-airflow-providers-docker apache-airflow standalone
