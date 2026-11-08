"""Deterministic local substitute for the future Integrante 2 detector."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from contracts import Alert, Transaction, utc_now


class LocalDetectorSimulator:
    """Apply transparent rules; replace this class with the real detector later."""

    def __init__(self, amount_threshold: float = 100.0, window_minutes: int = 5) -> None:
        self.amount_threshold = amount_threshold
        self.window = timedelta(minutes=window_minutes)

    def detect(
        self, transaction: Transaction, previous: Iterable[Transaction] = ()
    ) -> Alert | None:
        reasons: list[str] = []
        if transaction.amount < 0:
            reasons.append("El importe es negativo.")
        if abs(transaction.amount) >= self.amount_threshold:
            reasons.append(f"El importe alcanza o supera {self.amount_threshold:.2f}.")
        if transaction.errors:
            reasons.append(f"El registro contiene el error indicado: {transaction.errors}.")
        current_time = datetime.fromisoformat(transaction.date)
        rapid_count = sum(
            1
            for item in previous
            if item.client_id == transaction.client_id
            and abs(current_time - datetime.fromisoformat(item.date)) <= self.window
        )
        if rapid_count >= 2:
            reasons.append("Se observan varias transacciones del cliente en una ventana de 5 minutos.")
        if not reasons:
            return None
        return Alert(
            alert_id=f"alert-{transaction.id}",
            transaction=transaction,
            rule="local-simulator-rules",
            reasons=tuple(reasons),
            severity="medium" if len(reasons) < 2 else "high",
            detected_at=utc_now(),
        )
