import io
import json
from pathlib import Path

import pytest

from contracts import Alert, Metrics, Transaction
from detection.simulator import LocalDetectorSimulator
from genai.explainer import MockExplainer
from producer.producer import produce_events
from storage.storage import LocalStorage


ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "transactions_data_muestra.csv"


def producer_transaction():
    stream = io.StringIO()
    assert produce_events(CSV, stream, 1, 0) == 1
    return json.loads(stream.getvalue())


def test_real_producer_format_is_accepted():
    transaction = Transaction.from_dict(producer_transaction())
    assert transaction.id == 7475327
    assert transaction.amount == -77.0
    assert transaction.zip == "58523"


def test_transaction_validation_rejects_missing_or_wrong_fields():
    data = producer_transaction()
    del data["amount"]
    with pytest.raises(ValueError, match="amount"):
        Transaction.from_dict(data)
    data = producer_transaction()
    data["client_id"] = "not-an-int"
    with pytest.raises(ValueError, match="client_id"):
        Transaction.from_dict(data)
    data = producer_transaction()
    data["date"] = "not-a-date"
    with pytest.raises(ValueError, match="date"):
        Transaction.from_dict(data)


def test_simulator_and_mock_explanation_are_deterministic():
    transaction = Transaction.from_dict(producer_transaction())
    alert = LocalDetectorSimulator().detect(transaction)
    assert isinstance(alert, Alert)
    assert "negativo" in alert.reasons[0]
    explanation = MockExplainer().explain(alert)
    assert explanation.provider == "mock"
    assert "no confirma fraude" in explanation.recommendation
    assert explanation.evidence == alert.reasons


def test_alert_explanation_and_metrics_are_saved_locally(tmp_path):
    transaction = Transaction.from_dict(producer_transaction())
    alert = LocalDetectorSimulator().detect(transaction)
    assert alert is not None
    explanation = MockExplainer().explain(alert)
    metrics = Metrics("run-test", "start", "finish", 1, 1, 1, 0, 0)
    storage = LocalStorage(tmp_path)
    storage.save_alert(alert)
    storage.save_explanation(explanation)
    storage.save_metrics(metrics)
    assert json.loads((tmp_path / "alerts" / "alert-7475327.json").read_text())["alert_id"] == alert.alert_id
    assert json.loads((tmp_path / "explanations" / "alert-7475327.json").read_text())["provider"] == "mock"
    assert json.loads((tmp_path / "metrics" / "run-test.json").read_text())["alerts_generated"] == 1


def test_invalid_contracts_are_rejected():
    transaction = Transaction.from_dict(producer_transaction())
    with pytest.raises(ValueError, match="reasons"):
        Alert("alert-1", transaction, "rule", (), "medium", "now")
    with pytest.raises(ValueError, match="negative"):
        Metrics("run", "start", "finish", -1, 0, 0, 0, 0)


def test_pipeline_processes_real_csv_and_limits_explanations(tmp_path):
    from scripts.run_local_pipeline import run

    metrics = run(CSV, 10, 1, tmp_path)
    assert metrics.transactions_read == 10
    assert metrics.alerts_generated >= 1
    assert metrics.explanations_generated == 1
    assert len(list((tmp_path / "alerts").glob("*.json"))) == metrics.alerts_generated
    assert len(list((tmp_path / "explanations").glob("*.json"))) == 1
