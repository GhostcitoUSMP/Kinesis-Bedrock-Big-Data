import argparse
import csv
import json
import math
import random
import sys
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TextIO


REQUIRED_COLUMNS = {
    "id",
    "date",
    "client_id",
    "card_id",
    "amount",
    "use_chip",
    "merchant_id",
    "merchant_city",
    "merchant_state",
    "zip",
    "mcc",
    "errors",
}


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def non_negative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite number that is zero or greater")
    return number


def postal_code(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return value
    if number.is_finite() and number == number.to_integral_value():
        return f"{int(number):05d}" if 0 <= number < 100000 else str(int(number))
    return value


def transaction_event(row: dict[str, str], row_number: int) -> dict[str, object]:
    try:
        amount = Decimal(row["amount"].strip().replace("$", "").replace(",", ""))
        if not amount.is_finite():
            raise InvalidOperation
        timestamp = datetime.fromisoformat(row["date"].strip()).isoformat()
        return {
            "id": int(row["id"]),
            "date": timestamp,
            "client_id": int(row["client_id"]),
            "card_id": int(row["card_id"]),
            "amount": float(amount),
            "use_chip": row["use_chip"].strip(),
            "merchant_id": int(row["merchant_id"]),
            "merchant_city": row["merchant_city"].strip() or None,
            "merchant_state": row["merchant_state"].strip() or None,
            "zip": postal_code(row["zip"]),
            "mcc": int(row["mcc"]),
            "errors": row["errors"].strip() or None,
        }
    except (InvalidOperation, ValueError, KeyError) as error:
        raise ValueError(f"invalid data in CSV record {row_number}: {error}") from error


def read_events(csv_path: Path, limit: int | None = None):
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ValueError("CSV file is empty or has no header")
        missing_columns = REQUIRED_COLUMNS.difference(reader.fieldnames)
        if missing_columns:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing_columns))}")

        emitted = 0
        for row_number, row in enumerate(reader, start=2):
            if limit is not None and emitted >= limit:
                break
            if None in row:
                raise ValueError(f"unexpected extra CSV values in record {row_number}")
            if any(value is None for value in row.values()):
                raise ValueError(f"missing CSV values in record {row_number}")
            yield transaction_event(row, row_number)
            emitted += 1


def send_to_kinesis(events, stream_name: str, interval_seconds: float) -> int:
    try:
        import boto3
    except ImportError as error:
        raise RuntimeError("Install dependencies with: python -m pip install -r requirements.txt") from error

    client = boto3.client("kinesis")
    sent = 0
    batch_size = 1 if interval_seconds else 500
    batch = []

    def send_batch(records):
        nonlocal sent
        pending = records
        for attempt in range(6):
            response = client.put_records(StreamName=stream_name, Records=pending)
            failed = [
                (record, result)
                for record, result in zip(pending, response["Records"])
                if "ErrorCode" in result
            ]
            sent += len(pending) - len(failed)
            if not failed:
                break
            if attempt == 5:
                reasons = ", ".join(result.get("ErrorCode", "unknown") for _, result in failed)
                raise RuntimeError(f"Kinesis rejected {len(failed)} record(s): {reasons}")
            pending = [record for record, _ in failed]
            time.sleep(min(2**attempt, 10) + random.random())

    for event in events:
        batch.append({
            "Data": json.dumps(event, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            "PartitionKey": str(event["card_id"]),
        })
        if len(batch) == batch_size:
            send_batch(batch)
            batch = []
            if interval_seconds:
                time.sleep(interval_seconds)
    if batch:
        send_batch(batch)
    return sent


def demo_anomaly_events():
    window = datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()
    for index in range(5):
        yield {
            "id": -(int(time.time()) * 10 + index),
            "date": window,
            "client_id": -1,
            "card_id": -999,
            "amount": 20.0 + index,
            "use_chip": "Demo Transaction",
            "merchant_id": -1,
            "merchant_city": None,
            "merchant_state": None,
            "zip": None,
            "mcc": 0,
            "errors": None,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit transaction events locally or to Amazon Kinesis.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "transactions_data_muestra.csv",
        help="input CSV path",
    )
    parser.add_argument("--output", type=Path, help="write JSONL locally (default: stdout)")
    parser.add_argument("--stream-name", help="send events to this Kinesis stream instead of local output")
    parser.add_argument("--limit", type=positive_int, help="maximum number of events to emit")
    parser.add_argument(
        "--interval",
        type=non_negative_float,
        default=0,
        help="seconds between sends; forces one-event Kinesis batches",
    )
    parser.add_argument(
        "--demo-anomaly",
        action="store_true",
        help="after the CSV, send five clearly synthetic transactions for one card and minute",
    )
    args = parser.parse_args()

    try:
        events = read_events(args.input, args.limit)
        if args.stream_name:
            if args.output:
                parser.error("--output cannot be combined with --stream-name")
            sent = send_to_kinesis(events, args.stream_name, args.interval)
            if args.demo_anomaly:
                sent += send_to_kinesis(demo_anomaly_events(), args.stream_name, 0)
        else:
            if args.demo_anomaly:
                parser.error("--demo-anomaly requires --stream-name")
            if args.interval:
                source_events = events

                def paced_events():
                    for event in source_events:
                        yield event
                        time.sleep(args.interval)
                events = paced_events()
            output_context = (
                args.output.open("w", encoding="utf-8", newline="")
                if args.output
                else nullcontext(sys.stdout)
            )
            sent = 0
            with output_context as output:
                for event in events:
                    output.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
                    output.flush()
                    sent += 1
    except (OSError, ValueError, RuntimeError, csv.Error) as error:
        parser.exit(2, f"error: {error}\n")

    print(f"Emitted {sent} event(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
