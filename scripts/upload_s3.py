"""upload_s3: tar the run dir and upload to S3-compatible object storage.

Guarded: if S3_BUCKET is unset it prints "local" and exits 0 (Phase 1/2 stay usable
without object storage). Prints the artifact URI as the LAST stdout line -> XCom ->
logged to MLflow by log_mlflow.py.

Env:
  S3_BUCKET        target bucket (required to actually upload)
  S3_PREFIX        optional key prefix (default "runs")
  S3_ENDPOINT_URL  S3-compatible endpoint (e.g. Nebius: https://storage.eu-north1.nebius.cloud)
  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY  credentials (standard boto3 env)

Usage: python scripts/upload_s3.py runs/<run-id>
"""

import os
import sys
import tarfile
import tempfile
from pathlib import Path


def main(run_dir: str) -> None:
    run_dir = Path(run_dir)
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        print("local")  # nothing configured; local runs/ folder is the artifact
        return

    import boto3  # imported lazily so the guarded path needs no dependency

    prefix = os.environ.get("S3_PREFIX", "runs").strip("/")
    key = f"{prefix}/{run_dir.name}.tar.gz"

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        with tarfile.open(tmp.name, "w:gz") as tar:
            tar.add(run_dir, arcname=run_dir.name)
        s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT_URL"))
        s3.upload_file(tmp.name, bucket, key)
    Path(tmp.name).unlink(missing_ok=True)

    print(f"s3://{bucket}/{key}")  # last line -> XCom


if __name__ == "__main__":
    main(sys.argv[1])
