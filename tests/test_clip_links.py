import json
from pathlib import Path


from lumia_briefing_room.api.clips import find_clip, scan_clips
from lumia_briefing_room.pipeline import clip_files as cf
from tests_helpers_mp4 import mp4_with_comment


def put_meta(lib: Path, clip_id: str, **extra):
    lib.mkdir(parents=True, exist_ok=True)
    (lib / f"{clip_id}.json").write_text(json.dumps({"title": clip_id, **extra}), encoding="utf-8")


def put_video(path: Path, content: bytes = b"video", uid: str | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(mp4_with_comment(f"lumia:clipUid={uid}") + content if uid else content)
    return path


def ids(clips):
    return sorted(c.id for c in clips)


def test_a_renamed_and_moved_tagged_clip_is_found_by_its_uid(tmp_path):
    lib, root = tmp_path / "lib", tmp_path / "clips"
    put_meta(lib, "a", clipUid="U1")
    moved = put_video(root / "캐릭터" / "내가 바꾼 이름.mp4", uid="U1")
    (clip,) = scan_clips(lib, [root])
    assert clip.id == "a" and clip.video == moved
    assert find_clip(lib, "a", [root]).video == moved


def test_untagged_legacy_clip_is_found_by_file_name(tmp_path):
    lib, root = tmp_path / "lib", tmp_path / "clips"
    put_meta(lib, "a")
    video = put_video(root / "sub" / "a.mp4")
    assert scan_clips(lib, [root])[0].video == video


def test_a_clip_with_a_uid_is_not_stolen_by_a_json_with_the_same_file_name(tmp_path):
    lib, root = tmp_path / "lib", tmp_path / "clips"
    put_meta(lib, "a", clipUid="U1")
    put_meta(lib, "b", clipUid="U2")
    va = put_video(root / "b.mp4", uid="U1")
    vb = put_video(root / "x" / "whatever.mp4", uid="U2")
    by_id = {c.id: c.video for c in scan_clips(lib, [root])}
    assert by_id == {"a": va, "b": vb}


def test_renamed_legacy_clip_is_found_by_the_recorded_fingerprint(tmp_path):
    lib, root = tmp_path / "lib", tmp_path / "clips"
    original = put_video(root / "a.mp4", content=b"legacy clip content" * 100)
    fingerprint, size = cf.content_fingerprint(original), original.stat().st_size
    put_meta(lib, "a", videoFingerprint=fingerprint, videoSizeBytes=size)
    renamed = root / "폴더" / "완전히 다른 이름.mp4"
    renamed.parent.mkdir()
    original.rename(renamed)
    (clip,) = scan_clips(lib, [root])
    assert clip.video == renamed
    assert find_clip(lib, "a", [root]).video == renamed


def test_fingerprints_are_only_computed_for_videos_of_the_same_size(tmp_path, monkeypatch):
    lib, root = tmp_path / "lib", tmp_path / "clips"
    put_video(root / "other1.mp4", content=b"x" * 50)
    put_video(root / "other2.mp4", content=b"y" * 60)
    target = put_video(root / "target.mp4", content=b"z" * 70)
    put_meta(lib, "a", videoFingerprint=cf.content_fingerprint(target), videoSizeBytes=target.stat().st_size)
    target.rename(root / "renamed.mp4")
    seen = []
    real = cf.content_fingerprint
    monkeypatch.setattr(cf, "content_fingerprint", lambda p: (seen.append(p.name), real(p))[1])
    scan_clips(lib, [root])
    assert seen == ["renamed.mp4"]


def test_copies_with_the_same_uid_are_all_listed_and_share_the_info(tmp_path):
    lib, root = tmp_path / "lib", tmp_path / "clips"
    put_meta(lib, "a", clipUid="U1", title="공유 제목")
    first = put_video(root / "a.mp4", uid="U1")
    copy = put_video(root / "백업" / "a 복사본.mp4", uid="U1")
    clips = scan_clips(lib, [root])
    assert len(clips) == 2 and {c.video for c in clips} == {first, copy}
    primary = next(c for c in clips if c.id == "a")
    extra = next(c for c in clips if c.id != "a")
    assert primary.video == first and extra.id.startswith("a~") and extra.meta["title"] == "공유 제목"
    assert extra.meta_path == primary.meta_path
    assert find_clip(lib, extra.id, [root]).video == copy


def test_unknown_videos_are_listed_with_content_based_ids(tmp_path):
    lib, root = tmp_path / "lib", tmp_path / "clips"
    put_meta(lib, "a", clipUid="U1")
    put_video(root / "a.mp4", uid="U1")
    obs = put_video(root / "OBS" / "2026-09-30 방송.mp4", content=b"obs recording" * 50)
    unknown = cf.unknown_videos([lib], [root])
    assert [(u.path, u.id) for u in unknown] == [(obs, f"x_{cf.content_fingerprint(obs)}")]


def test_identical_unknown_files_get_distinct_ids(tmp_path):
    root = tmp_path / "clips"
    a = put_video(root / "a.mp4", content=b"same" * 20)
    b = put_video(root / "b.mp4", content=b"same" * 20)
    unknown = cf.unknown_videos([tmp_path / "lib"], [root])
    assert len({u.id for u in unknown}) == 2 and {u.path for u in unknown} == {a, b}


def test_a_json_made_for_an_unknown_video_links_it_by_fingerprint(tmp_path):
    lib, root = tmp_path / "lib", tmp_path / "clips"
    obs = put_video(root / "방송.mp4", content=b"obs" * 100)
    fp = cf.content_fingerprint(obs)
    put_meta(lib, f"x_{fp}", title="내가 붙인 제목", videoFingerprint=fp, videoSizeBytes=obs.stat().st_size)
    assert cf.unknown_videos([lib], [root]) == []
    (clip,) = scan_clips(lib, [root])
    assert clip.id == f"x_{fp}" and clip.video == obs


def test_find_unknown_by_id(tmp_path):
    root = tmp_path / "clips"
    obs = put_video(root / "방송.mp4", content=b"obs" * 100)
    (u,) = cf.unknown_videos([tmp_path / "lib"], [root])
    assert cf.find_unknown(u.id, [tmp_path / "lib"], [root]).path == obs
    assert cf.find_unknown("x_nope", [tmp_path / "lib"], [root]) is None


def test_fingerprints_are_recorded_for_untagged_clips_only_once(tmp_path):
    from lumia_briefing_room.pipeline.clip_fingerprint import pending_fingerprints, store_fingerprint

    lib, root = tmp_path / "lib", tmp_path / "clips"
    put_meta(lib, "old")
    put_meta(lib, "new", clipUid="U1")
    put_meta(lib, "gone")
    put_video(root / "old.mp4", content=b"legacy" * 50)
    put_video(root / "tagged.mp4", uid="U1")
    todo = pending_fingerprints(lib, [root])
    assert [m.stem for m, _ in todo] == ["old"], "태그가 있는 클립·영상이 없는 정보는 할 일이 아니다"
    assert store_fingerprint(*todo[0]) is True
    meta = json.loads((lib / "old.json").read_text(encoding="utf-8"))
    assert meta["videoFingerprint"] and meta["videoSizeBytes"] == (root / "old.mp4").stat().st_size
    assert pending_fingerprints(lib, [root]) == [] and store_fingerprint(*todo[0]) is False


def test_recorded_fingerprint_keeps_the_clip_after_a_rename_end_to_end(tmp_path):
    from lumia_briefing_room.pipeline.clip_fingerprint import pending_fingerprints, store_fingerprint

    lib, root = tmp_path / "lib", tmp_path / "clips"
    put_meta(lib, "old", title="내 제목", userLabel="pvp")
    video = put_video(root / "old.mp4", content=b"legacy" * 50)
    for pair in pending_fingerprints(lib, [root]):
        store_fingerprint(*pair)
    moved = root / "아야" / "이름 바꿈.mp4"
    moved.parent.mkdir()
    video.rename(moved)
    (clip,) = scan_clips(lib, [root])
    assert clip.video == moved and clip.meta["title"] == "내 제목" and clip.meta["userLabel"] == "pvp"
