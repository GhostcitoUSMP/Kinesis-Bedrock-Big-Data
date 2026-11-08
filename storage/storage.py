"""Common local JSON and Amazon S3 storage adapters."""

from __future__ import annotations

import json
import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from contracts import Alert, Explanation, Metrics


class StorageError(RuntimeError):
    """Raised when a document cannot be persisted."""


class Storage(ABC):
    @abstractmethod
    def save_alert(self, alert: Alert) -> str: ...

    @abstractmethod
    def save_explanation(self, explanation: Explanation) -> str: ...

    @abstractmethod
    def save_metrics(self, metrics: Metrics) -> str: ...


class LocalStorage(Storage):
    def __init__(self, root: Path | str = "output") -> None:
        self.root = Path(root)
        for directory in ("alerts", "explanations", "metrics"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

    def _save(self, kind: str, identifier: str, value: dict[str, Any]) -> str:
        path = self.root / kind / f"{identifier}.json"
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            temporary.replace(path)
        except OSError as error:
            raise StorageError(f"could not save {path}: {error}") from error
        return str(path)

    def save_alert(self, alert: Alert) -> str:
        return self._save("alerts", alert.alert_id, alert.to_dict())

    def save_explanation(self, explanation: Explanation) -> str:
        return self._save("explanations", explanation.alert_id, explanation.to_dict())

    def save_metrics(self, metrics: Metrics) -> str:
        return self._save("metrics", metrics.run_id, metrics.to_dict())


class S3Storage(Storage):
    def __init__(self, bucket: str | None = None, client: Any | None = None) -> None:
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError as error:
            raise StorageError("boto3 is required for S3 mode") from error
        self._aws_errors = (BotoCoreError, ClientError)
        self.bucket = bucket or os.getenv("S3_BUCKET")
        if not self.bucket:
            raise StorageError("S3_BUCKET is required")
        self.client = client or boto3.client("s3", region_name=os.getenv("AWS_REGION"))

    def _save(self, kind: str, identifier: str, value: dict[str, Any]) -> str:
        date = datetime.now().strftime("%Y-%m-%d")
        key = f"{kind}/{date}/{identifier}.json"
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=(json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(),
                ContentType="application/json",
            )
        except self._aws_errors as error:
            raise StorageError(f"could not save s3://{self.bucket}/{key}: {error}") from error
        return f"s3://{self.bucket}/{key}"

    def save_alert(self, alert: Alert) -> str:
        return self._save("alerts", alert.alert_id, alert.to_dict())

    def save_explanation(self, explanation: Explanation) -> str:
        return self._save("explanations", explanation.alert_id, explanation.to_dict())

    def save_metrics(self, metrics: Metrics) -> str:
        return self._save("metrics", metrics.run_id, metrics.to_dict())


def create_storage(mode: str | None = None, root: Path | str = "output") -> Storage:
    selected = (mode or os.getenv("STORAGE_MODE", "local")).lower()
    if selected == "local":
        return LocalStorage(root)
    if selected == "s3":
        return S3Storage()
    raise StorageError(f"unsupported STORAGE_MODE: {selected}")
