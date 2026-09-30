from test_api_games import KEY, client  # noqa: F401  (같은 게임 픽스처를 쓴다)

from lumia_briefing_room.pipeline.label_note import MEMO_MAX, normalize_memo


def _archive(client):
    return client.post(f"/api/games/{KEY}/candidates/{KEY}_01/save").json()["clipId"]


def test_memo_is_normalized_with_a_generous_limit():
    assert MEMO_MAX == 5000
    assert normalize_memo(None) is None and normalize_memo("   ") is None
    assert normalize_memo("  좋았다  ") == "좋았다"
    assert len(normalize_memo("가" * 6000)) == 5000
    assert normalize_memo("줄1\n줄2") == "줄1\n줄2"


def test_memo_can_be_written_read_and_cleared_through_the_clip_api(client):
    clip_id = _archive(client)
    assert client.patch(f"/api/clips/{clip_id}", json={"memo": "궁극기 타이밍이 좋았다"}).status_code == 200
    assert client.get(f"/api/clips/{clip_id}").json()["memo"] == "궁극기 타이밍이 좋았다"
    client.patch(f"/api/clips/{clip_id}", json={"memo": ""})
    assert client.get(f"/api/clips/{clip_id}").json().get("memo") is None


def test_memo_is_independent_of_the_label_note_and_survives_label_changes(client):
    clip_id = _archive(client)
    client.patch(f"/api/clips/{clip_id}", json={"memo": "개인 메모"})
    client.patch(f"/api/clips/{clip_id}", json={"userLabel": "pvp", "labelNote": "라벨 메모"})
    client.patch(f"/api/clips/{clip_id}", json={"userLabel": None})
    clip = client.get(f"/api/clips/{clip_id}").json()
    assert clip["memo"] == "개인 메모" and clip.get("labelNote") is None
    client.patch(f"/api/clips/{clip_id}", json={"labelNote": "다시"})
    assert client.get(f"/api/clips/{clip_id}").json()["memo"] == "개인 메모"


def test_memo_type_is_validated(client):
    clip_id = _archive(client)
    assert client.patch(f"/api/clips/{clip_id}", json={"memo": 123}).status_code == 400


def test_game_detail_reports_the_memo_of_each_archived_candidate(client):
    clip_id = _archive(client)
    client.patch(f"/api/clips/{clip_id}", json={"memo": "메모"})
    cands = {c["id"]: c for c in client.get(f"/api/games/{KEY}").json()["candidates"]}
    assert cands[f"{KEY}_01"]["user"]["savedMemo"] == "메모"
    assert "savedMemo" not in cands[f"{KEY}_02"]["user"]


def test_memo_survives_resaving_with_a_new_range(client):
    clip_id = _archive(client)
    client.patch(f"/api/clips/{clip_id}", json={"memo": "유지"})
    client.patch(f"/api/games/{KEY}/candidates/{KEY}_01", json={"start": 90, "end": 150})
    client.post(f"/api/games/{KEY}/candidates/{KEY}_01/save")
    assert client.get(f"/api/clips/{clip_id}").json()["memo"] == "유지"
