"""개발/배포 모드 판별. (plan-deploy.md D2)"""

MODES = ("dev", "release")


def resolve_mode(setting: str | None, *, frozen: bool) -> str:
    """`app.mode` 가 dev/release 면 그대로, 그 외(auto 포함)는 빌드본이냐로 정한다."""
    if setting in MODES:
        return setting
    return "release" if frozen else "dev"
