"""트레이 상주. (SPEC §6 2단계, §7.7 ui.startMinimized)

메뉴 구조(build_menu)는 순수하게 만든다. 실제로 도는 pystray.Icon.run() 이벤트
루프는 배선일 뿐이다 — GUI 이벤트 루프라 자동 테스트가 불가능하다.
"""

from collections.abc import Callable

import pystray
from PIL import Image

from lumia_briefing_room import paths
from lumia_briefing_room.icon import app_icon_image


def default_icon_image(size: int = 64) -> Image.Image:
    return app_icon_image(size)


def build_menu(
    *,
    on_open: Callable[[], None],
    on_toggle_watch: Callable[[], None],
    watch_enabled: Callable[[], bool],
    on_quit: Callable[[], None],
    on_open_logs: Callable[[], None] | None = None,
) -> pystray.Menu:
    """SPEC §7.2.1: "트레이 아이콘에 감시 중 상태를 표시"를 체크마크로 반영한다."""
    items = [
        pystray.MenuItem("루미아 브리핑룸 열기", lambda icon, item: on_open(), default=True),
        pystray.MenuItem(
            "감시 중",
            lambda icon, item: on_toggle_watch(),
            checked=lambda item: watch_enabled(),
        ),
    ]
    if on_open_logs is not None:
        items.append(pystray.MenuItem("로그 폴더 열기", lambda icon, item: on_open_logs()))
    return pystray.Menu(*items, pystray.Menu.SEPARATOR, pystray.MenuItem("종료", lambda icon, item: on_quit()))


def build_icon(
    *,
    on_open: Callable[[], None],
    on_toggle_watch: Callable[[], None],
    watch_enabled: Callable[[], bool],
    on_quit: Callable[[], None],
    on_open_logs: Callable[[], None] | None = None,
    title: str = "루미아 브리핑룸",
) -> pystray.Icon:
    return pystray.Icon(
        paths.app_folder_name(),
        icon=default_icon_image(),
        title=f"{title} ({paths.profile()})" if paths.profile() else title,
        menu=build_menu(
            on_open=on_open,
            on_toggle_watch=on_toggle_watch,
            watch_enabled=watch_enabled,
            on_quit=on_quit,
            on_open_logs=on_open_logs,
        ),
    )
