"""공용 계약(P:\\infra\\contract)의 픽스처를 JSON Schema 와 서버 양쪽이 같게 판정하는지 검사한다.

valid 는 둘 다 받아야 하고, invalid 는 둘 다 거부해야 하고, dropped 는 스키마(앱 쪽)는 거부하지만
서버는 받아서 모르는 필드만 버려야 한다. 어느 한쪽이 바뀌면 이 테스트가 깨진다.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.config import Settings
from app.main import create_app

CONTRACT = Path(__file__).resolve().parents[3] / "contract"
SCHEMA = json.loads((CONTRACT / "receiver.schema.json").read_text(encoding="utf-8"))
TOKEN = "secret"

ENDPOINTS = {
    "labels": ("/v1/labels", "LabelBatch", "LabelResponse"),
    "logs": ("/v1/logs", "LogBatch", "LogResponse"),
    "diagnostics": ("/v1/diagnostics", "DiagnosticBundle", "DiagnosticResponse"),
}


def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]})


def _fixtures(kind: str, outcome: str):
    folder = CONTRACT / "fixtures" / kind / outcome
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def _cases(outcome: str):
    return [
        pytest.param(kind, path, id=f"{kind}/{path.stem}")
        for kind in ENDPOINTS
        for path in _fixtures(kind, outcome)
    ]


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path, api_tokens=(TOKEN,), max_body_bytes=1_000_000)
    return TestClient(create_app(settings)), tmp_path


def _post(c, kind, path):
    url = ENDPOINTS[kind][0]
    return c.post(url, json=json.loads(path.read_text(encoding="utf-8")), headers={"X-Api-Token": TOKEN})


def test_fixture_folders_are_not_empty():
    for kind in ENDPOINTS:
        assert _fixtures(kind, "valid") and _fixtures(kind, "invalid"), kind


@pytest.mark.parametrize("kind,path", _cases("valid"))
def test_valid_fixture_is_accepted_by_schema_and_server(client, kind, path):
    c, _ = client
    payload = json.loads(path.read_text(encoding="utf-8"))
    _, request_def, response_def = ENDPOINTS[kind]
    assert not list(_validator(request_def).iter_errors(payload))
    r = _post(c, kind, path)
    assert r.status_code == 200, r.text
    assert not list(_validator(response_def).iter_errors(r.json()))


@pytest.mark.parametrize("kind,path", _cases("invalid"))
def test_invalid_fixture_is_rejected_by_schema_and_server(client, kind, path):
    c, _ = client
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert list(_validator(ENDPOINTS[kind][1]).iter_errors(payload))
    assert _post(c, kind, path).status_code == 422


@pytest.mark.parametrize("kind,path", _cases("dropped"))
def test_dropped_fixture_is_rejected_by_schema_but_server_drops_unknown_fields(client, kind, path):
    c, _ = client
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert list(_validator(ENDPOINTS[kind][1]).iter_errors(payload))
    assert _post(c, kind, path).status_code == 200


def test_label_fields_match_the_schema():
    """서버 pydantic 모델의 필드 이름이 JSON Schema 와 정확히 같아야 한다(한쪽만 고치는 실수 방지)."""
    from app import schemas

    pairs = {
        "Label": schemas.Label, "LabelBatch": schemas.LabelBatch, "Environment": schemas.Environment,
        "LogEntry": schemas.LogEntry, "LogBatch": schemas.LogBatch, "DiagnosticBundle": schemas.DiagnosticBundle,
    }
    for name, model in pairs.items():
        assert set(model.model_fields) == set(SCHEMA["$defs"][name]["properties"]), name
