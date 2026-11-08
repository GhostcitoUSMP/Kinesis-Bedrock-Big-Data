"""Data contracts shared by detection, GenAI and storage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import math
from typing import Any


def _required_int(data: dict[str, Any], name: str) -> int:
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


@dataclass(frozen=True)
class Transaction:
    id: int
    date: str
    client_id: int
    card_id: int
    amount: float
    use_chip: str
    merchant_id: int
    merchant_city: str | None
    merchant_state: str | None
    zip: str | None
    mcc: int
    errors: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        if not isinstance(data, dict):
            raise ValueError("transaction must be an object")
        for field in ("date", "use_chip"):
            if not isinstance(data.get(field), str) or not data[field]:
                raise ValueError(f"{field} must be a non-empty string")
        if isinstance(data.get("amount"), bool) or not isinstance(data.get("amount"), (int, float)):
            raise ValueError("amount must be numeric")
        if not math.isfinite(float(data["amount"])):
            raise ValueError("amount must be finite")
        try:
            datetime.fromisoformat(data["date"])
        except ValueError as error:
            raise ValueError("date must be ISO 8601") from error
        values = {name: data.get(name) for name in cls.__dataclass_fields__}
        values.update(
            id=_required_int(data, "id"),
            client_id=_required_int(data, "client_id"),
            card_id=_required_int(data, "card_id"),
            merchant_id=_required_int(data, "merchant_id"),
            mcc=_required_int(data, "mcc"),
        )
        for field in ("merchant_city", "merchant_state", "zip", "errors"):
            if values[field] is not None and not isinstance(values[field], str):
                raise ValueError(f"{field} must be a string or null")
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Alert:
    alert_id: str
    transaction: Transaction
    rule: str
    reasons: tuple[str, ...]
    severity: str
    detected_at: str
    detector: str = "local-simulator"

    def __post_init__(self) -> None:
        if not self.alert_id or not self.reasons:
            raise ValueError("alert_id and reasons are required")
        if self.severity not in {"low", "medium", "high", "critical"}:
            raise ValueError("unsupported alert severity")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reasons"] = list(self.reasons)
        return result


@dataclass(frozen=True)
class Explanation:
    alert_id: str
    summary: str
    evidence: tuple[str, ...]
    recommendation: str
    provider: str
    generated_at: str

    def __post_init__(self) -> None:
        if not self.alert_id or not self.summary or not self.recommendation:
            raise ValueError("explanation text and alert_id are required")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence"] = list(self.evidence)
        return result


@dataclass(frozen=True)
class Metrics:
    run_id: str
    started_at: str
    finished_at: str
    transactions_read: int
    alerts_generated: int
    explanations_generated: int
    explanation_errors: int
    storage_errors: int

    def __post_init__(self) -> None:
        counters = (
            self.transactions_read,
            self.alerts_generated,
            self.explanations_generated,
            self.explanation_errors,
            self.storage_errors,
        )
        if any(value < 0 for value in counters):
            raise ValueError("metric counters cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now().astimezone().isoformat()
