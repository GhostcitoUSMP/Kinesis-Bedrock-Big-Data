import json
import os
from typing import Any


SYSTEM_PROMPT = (
    "You explain streaming transaction anomalies for an educational monitoring system. "
    "An anomaly is a behavior that merits review, not proof of fraud. Never claim a transaction "
    "is fraudulent. Use only the supplied aggregate metrics and rule. Do not infer identity or "
    "invent missing facts. Respond in Spanish with a concise explanation and one review suggestion."
)


def explain_anomaly(alert: dict[str, Any], client=None, model_id: str | None = None) -> str:
    model_id = model_id or os.environ.get("BEDROCK_MODEL_ID", "")
    if not model_id:
        raise ValueError("BEDROCK_MODEL_ID is required to request an explanation")
    if client is None:
        import boto3

        client = boto3.client("bedrock-runtime")
    response = client.converse(
        modelId=model_id,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[
            {
                "role": "user",
                "content": [{"text": json.dumps(alert, ensure_ascii=False, allow_nan=False)}],
            }
        ],
        inferenceConfig={"maxTokens": 250, "temperature": 0.2},
    )
    return response["output"]["message"]["content"][0]["text"].strip()
