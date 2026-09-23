# TODO 입력함

> 사용자가 자유롭게 적는 입력 전용 파일이다. `/todo-sync` 세션이 이 파일을 읽고
> 문서(SPEC / plan*.md / README)에 반영한다. **코드는 건드리지 않는다.**
>
> 형식: `- [ ] 내용` 한 줄이 한 항목. 보충 설명은 들여쓴 하위 줄에 적는다.

## 당장 구현

## 추후 구현

## 처리됨

<!-- /todo-sync 가 반영을 끝낸 항목을 "- [x] 내용 → 반영한 문서 §절" 형태로 옮긴다. -->

- [x] 볼륨 자동 저장 → plan-ui.md §0 (원인: `ui.port=auto` 로 origin 이 바뀜), SPEC §7.7 `ui.port`
- [x] 자동 삭제 기능 정리 기준 체크박스 UI → plan-ui.md §0
- [x] 브라우저 디버깅 환경 구축 → plan-ui.md §6
- [x] 저장 버튼 윈도우 내장으로 변경 → plan-ui.md §7, SPEC §6 v2 이후 후보
- [x] 설치 및 배포 간편화 → plan-ui.md §7, SPEC §6 v2 이후 후보
- [x] 호스팅 공유 시 자체 추출 클립 구분 → plan-ui.md §7, SPEC §6 v2 이후 후보
- [x] 개발과 배포 모드 분리 → plan-ui.md §7, SPEC §6 v2 이후 후보
- [x] 자동 정리 후 게임 기록 유지 (대화 중 추가) → plan-ui.md §0, SPEC §7.6 `retention.keepGameRecords`
- [x] 코드 수정 시 서버 자동 재시작 → plan-ui.md §0 (개발용 `dev.bat` + `tools/dev_run.py`, `run.bat` 은 유지)
