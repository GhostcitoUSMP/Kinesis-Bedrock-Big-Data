import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def store_alert(alert: dict[str, Any], client=None, bucket: str | None = None) -> str:
    bucket = bucket or os.environ.get("RESULTS_BUCKET", "")
    if not bucket:
        raise ValueError("RESULTS_BUCKET is required to store an alert")
    if client is None:
        import boto3

        client = boto3.client("s3")
    alert_id = str(alert["alert_id"])
    window_start = alert.get("window_start")
    if window_start:
        date_prefix = datetime.fromisoformat(window_start.replace("Z", "+00:00")).strftime("%Y/%m/%d")
    else:
        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    key = f"alerts/{date_prefix}/{alert_id}.json"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(alert, ensure_ascii=False, allow_nan=False, default=json_default).encode("utf-8"),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )
    return key
