import base64
import hashlib
import json
import os
import time
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from detection.detector import detect_anomalies, window_start
from genai.explainer import explain_anomaly
from storage.storage import store_alert


dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["STATE_TABLE"])


def _update_card_metrics(event: dict) -> tuple[dict, bool]:
    event_id = str(event["id"])
    card_id = str(event["card_id"])
    window = window_start(str(event["date"]))
    partition = f"WINDOW#{window}#CARD#{card_id}"
    receipt_key = {"pk": f"EVENT#{event_id}", "sk": "RECEIPT"}
    metrics_key = {"pk": partition, "sk": "METRICS"}
    amount = Decimal(str(event["amount"]))

    try:
        dynamodb.meta.client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": table.name,
                        "Item": {
                            "pk": {"S": receipt_key["pk"]},
                            "sk": {"S": receipt_key["sk"]},
                            "expires_at": {"N": str(int(time.time()) + 604800)},
                        },
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                },
                {
                    "Update": {
                        "TableName": table.name,
                        "Key": {"pk": {"S": partition}, "sk": {"S": "METRICS"}},
                        "UpdateExpression": (
                            "SET expires_at = :expires "
                            "ADD transaction_count :one, amount_total :amount, error_count :error"
                        ),
                        "ExpressionAttributeValues": {
                            ":one": {"N": "1"},
                            ":amount": {"N": str(amount)},
                            ":error": {"N": "1" if event.get("errors") else "0"},
                            ":expires": {"N": str(int(time.time()) + 2592000)},
                        },
                    }
                },
            ]
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        duplicate = table.get_item(Key=receipt_key, ConsistentRead=True).get("Item")
        if duplicate:
            metrics = table.get_item(Key=metrics_key, ConsistentRead=True).get("Item")
            if not metrics:
                raise RuntimeError(f"metrics missing for previously processed event {event_id}")
            _update_max_amount(metrics_key, amount)
            metrics = table.get_item(Key=metrics_key, ConsistentRead=True).get("Item")
            return metrics, True
        raise

    _update_max_amount(metrics_key, amount)

    metrics = table.get_item(Key=metrics_key, ConsistentRead=True).get("Item")
    if not metrics:
        raise RuntimeError(f"metrics missing after processing event {event_id}")
    return metrics, False


def _update_max_amount(metrics_key: dict, amount: Decimal) -> None:
    # Keep the maximum as a monotonic value; a lower concurrent amount cannot replace it.
    try:
        table.update_item(
            Key=metrics_key,
            UpdateExpression="SET amount_max = :amount",
            ConditionExpression="attribute_not_exists(amount_max) OR amount_max < :amount",
            ExpressionAttributeValues={":amount": amount},
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise

def _claim_alert(alert_id: str, window: str, card_id: str) -> bool:
    try:
        table.put_item(
            Item={
                "pk": f"ALERT#{alert_id}",
                "sk": "CLAIM",
                "window_start": window,
                "card_id": card_id,
                "status": "PROCESSING",
                "expires_at": int(time.time()) + 604800,
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
        return True
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def _complete_alert(alert_id: str) -> None:
    table.update_item(
        Key={"pk": f"ALERT#{alert_id}", "sk": "CLAIM"},
        UpdateExpression="SET #status = :complete",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":complete": "COMPLETE"},
    )


def _release_alert(alert_id: str) -> None:
    table.delete_item(Key={"pk": f"ALERT#{alert_id}", "sk": "CLAIM"})


def lambda_handler(event, context):
    threshold = int(os.environ.get("MAX_TX_PER_CARD_PER_MINUTE", "5"))
    stored = 0
    duplicates = 0
    for record in event.get("Records", []):
        transaction = json.loads(base64.b64decode(record["kinesis"]["data"]).decode("utf-8"))
        metrics, duplicate = _update_card_metrics(transaction)
        if duplicate:
            duplicates += 1

        anomaly_metrics = {
            "transaction_count": int(metrics["transaction_count"]),
            "window_seconds": 60,
        }
        rules = detect_anomalies(anomaly_metrics, threshold)
        if not rules:
            continue

        window = window_start(str(transaction["date"]))
        card_id = str(transaction["card_id"])
        alert_id = hashlib.sha256(f"{window}:{card_id}:card_velocity".encode()).hexdigest()
        if not _claim_alert(alert_id, window, card_id):
            continue

        alert = {
            "schema_version": "1.0",
            "alert_id": alert_id,
            "window_start": window,
            "window_seconds": 60,
            "card_id": card_id,
            "metrics": {
                "transaction_count": int(metrics["transaction_count"]),
                "amount_total": float(metrics["amount_total"]),
                "amount_average": round(
                    float(metrics["amount_total"]) / int(metrics["transaction_count"]), 2
                ),
                "amount_max": float(metrics.get("amount_max", transaction["amount"])),
                "error_count": int(metrics["error_count"]),
            },
            "rules": rules,
            "interpretation": "Comportamiento inusual que requiere revisión; no confirma fraude.",
        }
        try:
            if os.environ.get("BEDROCK_MODEL_ID"):
                explanation_input = {
                    key: value for key, value in alert.items()
                    if key not in {"alert_id", "card_id"}
                }
                alert["explanation"] = explain_anomaly(explanation_input)
            else:
                alert["explanation"] = None
                alert["explanation_status"] = "not_configured"
            alert["s3_key"] = store_alert(alert)
            _complete_alert(alert_id)
        except Exception:
            _release_alert(alert_id)
            raise
        stored += 1

    return {"processed": len(event.get("Records", [])), "duplicates": duplicates, "alerts_stored": stored}
