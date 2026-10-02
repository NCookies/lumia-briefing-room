"""첫 실행 화면과 사용 안내 — 문구·경고 상자·시작 버튼 조건."""

import re

from playwright.sync_api import expect


def test_F01_first_run_screen_warns_about_storage_and_blocks_start_until_confirmed(go, page, world, launch, shot):
    world.seed_default_games()
    server = launch(consented=False)
    page.goto(server.url)
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text(re.compile("50~100GB 여유 공간"))).to_be_visible()
    expect(page.get_by_text(re.compile("드라이브의 여유 공간"))).to_be_visible()
    shot("first_run")
    start = page.get_by_role("button", name=re.compile("시작하기"))
    expect(start).to_be_disabled()
    page.get_by_label(re.compile("확인했습니다")).check()
    expect(start).to_be_enabled()
    shot("first_run_confirmed")


def test_F02_guide_tabs_all_open(go, page, shot):
    go("/")
    page.get_by_label("사용 안내").click()
    dialog = page.get_by_role("dialog")
    tabs = ["시작하기", "풀영상 화면", "클립", "자동 정리", "영상 파일", "폴더", "단축키"]
    for name in tabs:
        dialog.get_by_text(name, exact=True).first.click()
        page.wait_for_timeout(150)
        text = dialog.inner_text()
        assert "`" not in text and "{" not in text, f"{name} 탭에 마크업 글자가 남아 있다"
        shot(f"guide_{name}")
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)


def test_F03_guide_folder_picture_uses_the_real_folder_names(go, page):
    go("/")
    page.get_by_label("사용 안내").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_text("폴더", exact=True).first.click()
    text = dialog.inner_text()
    for name in ("clips", "full_video", "steam_replay", "vod", "보관함", "자동 보관"):
        assert name in text, f"폴더 그림에 {name} 이 없다"
