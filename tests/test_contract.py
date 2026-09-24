"""서버와 공유하는 전송 계약(tests/contract, 원본은 infra 저장소)을 앱 쪽에서 검증한다.

앱이 새 메타데이터 필드를 추가하면 여기서 깨져서 "보낼지 말지"를 계약 분류표에 적게 만든다.
"""

import dataclasses
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from lumia_briefing_room.config import _to_camel
from lumia_briefing_room.pipeline.metadata import ClipMetadata

CONTRACT = Path(__file__).resolve().parent / "contract"
SCHEMA = json.loads((CONTRACT / "receiver.schema.json").read_text(encoding="utf-8"))
FIELDS = json.loads((CONTRACT / "app-metadata-fields.json").read_text(encoding="utf-8"))
BATCH_DEFS = {"labels": "LabelBatch", "logs": "LogBatch", "diagnostics": "DiagnosticBundle"}


def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]})


def _fixtures(outcome: str):
    return [
        pytest.param(kind, path, id=f"{kind}/{path.stem}")
        for kind in BATCH_DEFS
        for path in sorted((CONTRACT / "fixtures" / kind / outcome).glob("*.json"))
    ]


def _errors(kind: str, path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(_validator(BATCH_DEFS[kind]).iter_errors(payload))


@pytest.mark.parametrize("kind,path", _fixtures("valid"))
def test_valid_fixtures_satisfy_the_schema(kind, path):
    assert _errors(kind, path) == []


@pytest.mark.parametrize("kind,path", _fixtures("invalid") + _fixtures("dropped"))
def test_invalid_and_dropped_fixtures_break_the_schema(kind, path):
    assert _errors(kind, path)


def _camel_names() -> list[str]:
    return [_to_camel(f.name) for f in dataclasses.fields(ClipMetadata)]


def _classified() -> set[str]:
    converted = {key for key in FIELDS["converted"] if "+" not in key}
    return set(FIELDS["sent"]) | converted | set(FIELDS["excluded"])


def test_every_app_metadata_field_is_classified_as_sent_or_excluded():
    unclassified = set(_camel_names()) - _classified()
    assert not unclassified, f"전송 여부를 contract/app-metadata-fields.json 에 분류해야 한다: {sorted(unclassified)}"


def test_classification_has_no_stale_entries():
    stale = _classified() - set(_camel_names()) - {"labelNote"}
    assert not stale, f"앱에 없는 필드가 분류표에 있다: {sorted(stale)}"


def test_sent_fields_are_all_in_the_label_schema_and_excluded_ones_are_not():
    props = set(SCHEMA["$defs"]["Label"]["properties"])
    assert set(FIELDS["sent"]) <= props
    assert not props & set(FIELDS["excluded"])


def test_every_label_schema_field_is_explained():
    props = set(SCHEMA["$defs"]["Label"]["properties"])
    made_by_contract = {"userLabel", "labelNote", "matchKey", "clipKey"} | set(FIELDS["appMissing"])
    assert props == set(FIELDS["sent"]) | made_by_contract


def test_privacy_sensitive_fields_are_never_sent():
    banned = {"title", "sessionDir", "thumbnailPath", "matchStartUtc", "teamCharacters", "matchResult", "streamer"}
    assert not banned & set(SCHEMA["$defs"]["Label"]["properties"])


def test_vod_clip_extra_fields_are_classified_and_not_sent():
    from test_vod_clips import build

    vod_only = set(build()) - set(_camel_names())
    assert vod_only <= set(FIELDS["vodOnly"]["excluded"]), sorted(vod_only - set(FIELDS["vodOnly"]["excluded"]))
    assert not set(FIELDS["vodOnly"]["excluded"]) & set(SCHEMA["$defs"]["Label"]["properties"])
