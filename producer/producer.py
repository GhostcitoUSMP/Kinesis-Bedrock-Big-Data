import argparse
import csv
import json
import math
import sys
import time
from contextlib import nullcontext
from datetime import datetime
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
        return str(int(number))
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


def produce_events(
    csv_path: Path,
    output: TextIO,
    limit: int | None,
    interval_seconds: float,
) -> int:
    sent = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ValueError("CSV file is empty or has no header")
        missing_columns = REQUIRED_COLUMNS.difference(reader.fieldnames)
        if missing_columns:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing_columns))}")

        for row_number, row in enumerate(reader, start=2):
            if limit is not None and sent >= limit:
                break
            if None in row:
                raise ValueError(f"unexpected extra CSV values in record {row_number}")
            if any(value is None for value in row.values()):
                raise ValueError(f"missing CSV values in record {row_number}")
            event = transaction_event(row, row_number)
            output.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
            output.flush()
            sent += 1
            if interval_seconds and (limit is None or sent < limit):
                time.sleep(interval_seconds)

    return sent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read transactions from CSV and emit transaction events as JSONL locally."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).with_name("transactions_data_muestra.csv"),
        help="input CSV path (default: transactions_data_muestra.csv next to this script)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output JSONL path (default: write events to stdout)",
    )
    parser.add_argument("--limit", type=positive_int, help="maximum number of events to emit")
    parser.add_argument(
        "--interval",
        type=non_negative_float,
        default=0,
        help="seconds to wait between events (default: 0)",
    )
    args = parser.parse_args()

    output_context = args.output.open("w", encoding="utf-8", newline="") if args.output else nullcontext(sys.stdout)
    try:
        with output_context as output:
            sent = produce_events(args.input, output, args.limit, args.interval)
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(2, f"error: {error}\n")

    print(f"Emitted {sent} event(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
