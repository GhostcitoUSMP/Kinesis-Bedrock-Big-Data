"""Mock and Amazon Bedrock explanation providers."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from contracts import Alert, Explanation, utc_now


class ExplanationError(RuntimeError):
    """Raised when an explanation provider cannot return a valid explanation."""


class Explainer(ABC):
    @abstractmethod
    def explain(self, alert: Alert) -> Explanation:
        raise NotImplementedError


def _safe_prompt_data(alert: Alert) -> dict[str, Any]:
    transaction = alert.transaction
    return {
        "transaction_id": transaction.id,
        "date": transaction.date,
        "amount": transaction.amount,
        "use_chip": transaction.use_chip,
        "merchant_id": transaction.merchant_id,
        "merchant_city": transaction.merchant_city,
        "merchant_state": transaction.merchant_state,
        "mcc": transaction.mcc,
        "errors": transaction.errors,
        "rule": alert.rule,
        "reasons": list(alert.reasons),
        "severity": alert.severity,
    }


class MockExplainer(Explainer):
    def explain(self, alert: Alert) -> Explanation:
        amount = alert.transaction.amount
        summary = (
            f"La transacción {alert.transaction.id} presenta indicios de anomalía "
            f"por un importe de {amount:.2f}."
        )
        return Explanation(
            alert_id=alert.alert_id,
            summary=summary,
            evidence=alert.reasons,
            recommendation="Revisar la transacción y confirmar el contexto con el titular; "
            "la alerta no confirma fraude por sí sola.",
            provider="mock",
            generated_at=utc_now(),
        )


class BedrockExplainer(Explainer):
    def __init__(self, client: Any | None = None) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as error:
            raise ExplanationError("boto3 is required for Bedrock mode") from error
        region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION"))
        model_id = os.getenv("BEDROCK_MODEL_ID")
        if not region or not model_id:
            raise ExplanationError("AWS_REGION and BEDROCK_MODEL_ID are required")
        self.model_id = model_id
        self.client = client or boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=Config(
                connect_timeout=int(os.getenv("BEDROCK_CONNECT_TIMEOUT", "10")),
                read_timeout=int(os.getenv("BEDROCK_READ_TIMEOUT", "60")),
                retries={"max_attempts": 2},
            ),
        )

    def explain(self, alert: Alert) -> Explanation:
        prompt = (
            "Explica esta alerta financiera en español. Devuelve JSON con las claves "
            "summary, evidence (lista) y recommendation. Expresa indicios, nunca fraude "
            "confirmado. Datos: " + json.dumps(_safe_prompt_data(alert), ensure_ascii=False)
        )
        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(
                    {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 400,
                        "temperature": 0,
                        "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    }
                ),
            )
            raw = response["body"].read()
            payload = json.loads(raw)
            text = payload["content"][0]["text"]
            result = json.loads(text)
            if not isinstance(result.get("summary"), str) or not isinstance(
                result.get("evidence"), list
            ) or not isinstance(result.get("recommendation"), str):
                raise ValueError("missing explanation fields")
            return Explanation(
                alert_id=alert.alert_id,
                summary=result["summary"],
                evidence=tuple(str(item) for item in result["evidence"]),
                recommendation=result["recommendation"],
                provider=f"bedrock:{self.model_id}",
                generated_at=utc_now(),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError) as error:
            raise ExplanationError(f"invalid Bedrock response: {error}") from error


def create_explainer(mode: str | None = None) -> Explainer:
    selected = (mode or os.getenv("GENAI_MODE", "mock")).lower()
    if selected == "mock":
        return MockExplainer()
    if selected == "bedrock":
        return BedrockExplainer()
    raise ExplanationError(f"unsupported GENAI_MODE: {selected}")
