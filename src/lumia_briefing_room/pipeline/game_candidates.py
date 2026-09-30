"""게임 기록의 교전 후보 수정·선택 규칙. 사용자 수정은 `candidates[].user` 에만 쓰고 자동 검출 값은 그대로 둔다.
수정 기록은 구간 경계 단위의 정답 데이터가 된다. (plan-fullvideo.md §3.1)"""

from __future__ import annotations

MIN_LENGTH_SEC = 1.0
LABELS = ("combat", "hunt")
MAX_TITLE_LEN = 100
_EDITABLE = {"start", "end", "dismissed", "label", "title"}


def all_candidates(game: dict) -> list[dict]:
    return list(game.get("candidates") or []) + list(game.get("userCandidates") or [])


def find_candidate(game: dict, candidate_id: str) -> dict | None:
    return next((c for c in all_candidates(game) if c.get("id") == candidate_id), None)


def effective_range(cand: dict, duration_sec: float) -> tuple[float, float]:
    user = cand.get("user") or {}
    start = float(user.get("start", cand["start"]))
    end = float(user.get("end", cand["end"]))
    return max(0.0, start), min(duration_sec, end)


def effective_title(cand: dict) -> str:
    return (cand.get("user") or {}).get("title") or cand.get("title") or "직접 추가한 구간"


def range_changed(cand: dict, duration_sec: float) -> bool:
    """범위를 저장 당시(저장한 적 없으면 검출값)와 다르게 고쳤는가. 저장 범위 기록이 없는 옛 클립은 검출 범위로 만든 것으로 본다."""
    user = cand.get("user") or {}
    if "savedStart" in user and "savedEnd" in user and user.get("savedClipId"):
        base = (float(user["savedStart"]), float(user["savedEnd"]))
    else:
        base = (max(0.0, float(cand["start"])), min(duration_sec, float(cand["end"])))
    used = effective_range(cand, duration_sec)
    return abs(base[0] - used[0]) > 0.001 or abs(base[1] - used[1]) > 0.001


def apply_edit(cand: dict, patch: dict, duration_sec: float) -> None:
    unknown = set(patch) - _EDITABLE
    if unknown:
        raise ValueError(f"고칠 수 없는 항목입니다: {', '.join(sorted(unknown))}")
    user = dict(cand.get("user") or {})

    if "start" in patch or "end" in patch:
        current_start, current_end = effective_range({**cand, "user": user}, duration_sec)
        start = float(patch.get("start", current_start))
        end = float(patch.get("end", current_end))
        if start < 0 or end > duration_sec:
            raise ValueError("구간이 영상 길이를 벗어납니다")
        if end - start < MIN_LENGTH_SEC:
            raise ValueError(f"구간은 {MIN_LENGTH_SEC:g}초 이상이어야 합니다")
        user["start"], user["end"] = round(start, 3), round(end, 3)

    if "title" in patch:
        title = patch["title"]
        if title is not None and not isinstance(title, str):
            raise ValueError("이름은 글자여야 합니다")
        title = (title or "").strip()
        if len(title) > MAX_TITLE_LEN:
            raise ValueError(f"이름은 {MAX_TITLE_LEN}자 이하여야 합니다")
        if title:
            user["title"] = title
        else:
            user.pop("title", None)

    if "dismissed" in patch:
        if patch["dismissed"]:
            user["dismissed"] = True
        else:
            user.pop("dismissed", None)

    if "label" in patch:
        label = patch["label"]
        if label is None:
            user.pop("label", None)
        elif label in LABELS:
            user["label"] = label
        else:
            raise ValueError("알 수 없는 라벨입니다")

    cand["user"] = user


def new_user_candidate(game: dict, start: float, end: float, duration_sec: float, *, title: str | None = None) -> dict:
    if start < 0 or end > duration_sec or end - start < MIN_LENGTH_SEC:
        raise ValueError("구간이 올바르지 않습니다")
    key = game["gameKey"]
    number = 1 + max(
        (int(c["id"].rsplit("_u", 1)[1]) for c in game.get("userCandidates") or [] if "_u" in c.get("id", "")),
        default=0,
    )
    return {
        "id": f"{key}_u{number}",
        "start": round(start, 3),
        "end": round(end, 3),
        "title": title or "직접 추가한 구간",
        "tags": [],
        "certain": False,
        "user": {},
    }


def select_for_batch(game: dict, mode: str, *, ids: list[str] | None = None) -> list[dict]:
    """일괄 저장 대상: 무시하지 않았고 아직 저장하지 않은 후보 중 전부 / 확실한 것만 / 고른 것만."""
    if mode not in ("all", "certain", "ids"):
        raise ValueError("알 수 없는 일괄 저장 방식입니다")
    pending = [
        c for c in all_candidates(game)
        if not (c.get("user") or {}).get("dismissed") and not (c.get("user") or {}).get("savedClipId")
    ]
    if mode == "certain":
        return [c for c in pending if c.get("certain")]
    if mode == "ids":
        wanted = set(ids or [])
        return [c for c in pending if c["id"] in wanted]
    return pending
