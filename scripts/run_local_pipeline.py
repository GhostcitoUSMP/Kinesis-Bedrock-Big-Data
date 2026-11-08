"""Run producer transformation, local detection, mock GenAI and local storage."""

from __future__ import annotations

import argparse
import io
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts import Metrics, Transaction, utc_now
from detection.simulator import LocalDetectorSimulator
from genai.explainer import create_explainer
from producer.producer import produce_events
from storage.storage import StorageError, create_storage


def run(input_path: Path, limit: int | None, explanation_limit: int, output: Path) -> Metrics:
    started = utc_now()
    stream = io.StringIO()
    produce_events(input_path, stream, limit, 0)
    stream.seek(0)
    transactions = [Transaction.from_dict(json.loads(line)) for line in stream if line.strip()]
    detector = LocalDetectorSimulator()
    explainer = create_explainer("mock")
    storage = create_storage("local", output)
    alerts = 0
    explanations = 0
    explanation_errors = 0
    storage_errors = 0
    previous: list[Transaction] = []
    for transaction in transactions:
        alert = detector.detect(transaction, previous)
        previous.append(transaction)
        if alert is None:
            continue
        alerts += 1
        try:
            storage.save_alert(alert)
        except StorageError as error:
            storage_errors += 1
            print(f"storage error for {alert.alert_id}: {error}", file=sys.stderr)
            continue
        if explanations >= explanation_limit:
            continue
        try:
            explanation = explainer.explain(alert)
            storage.save_explanation(explanation)
            explanations += 1
        except (StorageError, RuntimeError) as error:
            explanation_errors += 1
            print(f"explanation error for {alert.alert_id}: {error}", file=sys.stderr)
    metrics = Metrics(
        run_id=f"run-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}",
        started_at=started,
        finished_at=utc_now(),
        transactions_read=len(transactions),
        alerts_generated=alerts,
        explanations_generated=explanations,
        explanation_errors=explanation_errors,
        storage_errors=storage_errors,
    )
    storage.save_metrics(metrics)
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "transactions_data_muestra.csv")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--explanation-limit", type=int, default=100)
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    if args.limit < 1 or args.explanation_limit < 0:
        parser.error("--limit must be positive and --explanation-limit cannot be negative")
    metrics = run(args.input, args.limit, args.explanation_limit, args.output)
    print(
        f"Procesadas: {metrics.transactions_read}; alertas: {metrics.alerts_generated}; "
        f"explicaciones: {metrics.explanations_generated}; salida: {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
