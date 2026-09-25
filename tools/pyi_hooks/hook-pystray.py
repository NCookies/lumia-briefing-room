"""pystray(LGPL v3)를 PYZ 아카이브가 아니라 `_internal/pystray/*.py` 로 풀어 넣는다.

사용자가 이 폴더의 파일을 고치거나 다른 버전으로 바꿔 넣을 수 있어야 LGPL 의 교체 가능성 요건을 만족한다
(plan-deploy.md §7-15). 실험: 풀린 __init__.py 를 고치면 실행 파일이 그 파일을 읽는다.
"""

module_collection_mode = "py"
