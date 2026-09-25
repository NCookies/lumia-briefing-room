"""분석할 수 있는 영상 확장자의 유일한 원본. 폴더 스캔·파일 선택창·화면 안내가 모두 이 목록을 쓴다. (plan-ui.md §0 확장자 도움말)"""

VIDEO_EXTENSIONS = frozenset({".mp4", ".mkv", ".ts", ".webm", ".mov"})
VERIFIED_EXTENSIONS = frozenset({".mp4"})


def sorted_extensions() -> list[str]:
    return sorted(VIDEO_EXTENSIONS)
