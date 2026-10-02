"""풀영상 화면 편집 — 범위 고치기·수정됨/저장 대기·다시 저장·실행 취소/다시 시도·후보 삭제와 복구·Ctrl+S."""

import re

from playwright.sync_api import expect

from e2e.world import KEY_BR
from e2e.test_viewer import open_game


def cand(page, n=0):
    return page.locator("[data-cand]").nth(n)


def archive(page, n=0):
    cand(page, n).get_by_role("button", name="보관").click()
    page.get_by_role("dialog").get_by_text("보관함").first.click()
    expect(cand(page, n).get_by_text("보관됨")).to_be_visible(timeout=20000)


def seek(page, sec):
    page.evaluate(f"() => {{ const v = document.querySelector('video'); v.pause(); v.currentTime = {sec} }}")
    page.wait_for_timeout(200)


def test_E01_ctrl_s_opens_the_archive_popup_and_blocks_the_browser_save(go, page, shot):
    open_game(page, go)
    page.evaluate("() => window.addEventListener('keydown', (e) => { window.__prevented = e.defaultPrevented })")
    cand(page).get_by_text("첫 교전").click()
    page.keyboard.press("Control+s")
    expect(page.get_by_role("dialog")).to_be_visible()
    assert page.evaluate("() => window.__prevented") is True
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)


def test_E02_editing_a_saved_range_marks_it_and_resave_replaces_the_same_clip(go, page, world, shot):
    open_game(page, go)
    archive(page)
    cand(page).get_by_text("첫 교전").click()
    seek(page, 5)
    page.keyboard.press("i")
    expect(cand(page)).to_contain_text("수정됨")
    expect(cand(page)).to_contain_text("0:05~0:09")
    resave = cand(page).get_by_role("button", name=re.compile("다시 저장"))
    expect(resave).to_be_visible()
    shot("range_edited")
    page.get_by_text("← 게임 목록").click()
    expect(page.locator(f'[data-game="{KEY_BR}"]')).to_contain_text("1개 저장 대기")
    page.locator(f'[data-game="{KEY_BR}"]').click()
    cand(page).get_by_role("button", name=re.compile("다시 저장")).click()
    expect(cand(page)).not_to_contain_text("수정됨", timeout=20000)
    assert len(list((world.root / "clips" / "보관함").glob("*.mp4"))) == 1, "다시 저장은 같은 클립을 교체한다(중복 금지)"
    page.get_by_text("← 게임 목록").click()
    expect(page.locator(f'[data-game="{KEY_BR}"]')).not_to_contain_text("저장 대기")


def test_E03_edit_is_not_marked_for_an_unsaved_candidate(go, page):
    open_game(page, go)
    cand(page, 1).get_by_text("20260930_002400_02").click()
    seek(page, 12)
    page.keyboard.press("i")
    expect(cand(page, 1)).to_contain_text("0:12~0:16")
    expect(cand(page, 1)).not_to_contain_text("저장 대기")


def test_E04_undo_and_redo_restore_the_range(go, page):
    open_game(page, go)
    archive(page)
    cand(page).get_by_text("첫 교전").click()
    seek(page, 5)
    page.keyboard.press("i")
    expect(cand(page)).to_contain_text("0:05~0:09")
    page.keyboard.press("Control+z")
    expect(cand(page)).to_contain_text("0:03~0:09")
    expect(cand(page)).not_to_contain_text("수정됨")
    page.keyboard.press("Control+y")
    expect(cand(page)).to_contain_text("0:05~0:09")


def test_E05_deleting_an_unsaved_candidate_hides_it_and_undo_brings_it_back(go, page, shot):
    open_game(page, go)
    box = page.get_by_test_id("viewer-candidates")
    cand(page, 1).get_by_role("button", name="삭제").click()
    expect(box).to_contain_text("후보 2개")
    expect(box).not_to_contain_text("20260930_002400_02")
    page.get_by_label("삭제한 후보도 보기").check()
    expect(box).to_contain_text("20260930_002400_02")
    page.get_by_label("삭제한 후보도 보기").uncheck()
    page.locator("body").click(position={"x": 5, "y": 5})
    page.keyboard.press("Control+z")
    expect(box).to_contain_text("후보 3개")
    shot("deleted_then_undone")


def test_E06_add_a_range_then_it_can_be_archived(go, page):
    open_game(page, go)
    seek(page, 20)
    page.get_by_role("button", name="여기서 구간 추가").click()
    box = page.get_by_test_id("viewer-candidates")
    expect(box).to_contain_text("후보 4개")
    new = page.locator("[data-cand]").last
    new.get_by_role("button", name="보관").click()
    page.get_by_role("dialog").get_by_text("보관함").first.click()
    expect(page.locator("[data-cand]").filter(has_text="보관됨")).to_have_count(1, timeout=20000)
