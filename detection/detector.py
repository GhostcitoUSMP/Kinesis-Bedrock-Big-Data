from datetime import datetime, timezone
from typing import Any


def window_start(timestamp: str, window_seconds: int = 60) -> str:
    if window_seconds < 1:
        raise ValueError("window_seconds must be greater than zero")
    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    epoch = int(parsed.timestamp())
    start = epoch - epoch % window_seconds
    return datetime.fromtimestamp(start, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def transaction_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        raise ValueError("at least one event is required")
    amounts = [float(event["amount"]) for event in events]
    return {
        "transaction_count": len(events),
        "amount_total": round(sum(amounts), 2),
        "amount_average": round(sum(amounts) / len(amounts), 2),
        "amount_max": round(max(amounts), 2),
        "error_count": sum(bool(event.get("errors")) for event in events),
    }


def detect_anomalies(
    metrics: dict[str, Any],
    max_transactions_per_card_per_window: int = 5,
) -> list[dict[str, Any]]:
    if max_transactions_per_card_per_window < 1:
        raise ValueError("max_transactions_per_card_per_window must be greater than zero")
    count = int(metrics["transaction_count"])
    if count < max_transactions_per_card_per_window:
        return []
    return [
        {
            "rule_id": "card_velocity",
            "severity": "medium",
            "description": (
                f"{count} transactions for one card in the same "
                f"{metrics.get('window_seconds', 60)}-second window"
            ),
        }
    ]
