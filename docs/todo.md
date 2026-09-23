# TODO 입력함

> 사용자가 자유롭게 적는 입력 전용 파일이다. `/todo-sync` 세션이 이 파일을 읽고
> 문서(SPEC / plan*.md / README)에 반영한다. **코드는 건드리지 않는다.**
>
> 형식: `- [ ] 내용` 한 줄이 한 항목. 보충 설명은 들여쓴 하위 줄에 적는다.

## 당장 구현

- [ ] 접속 주소를 `localhost` 대신 `lumia-briefingroom.localhost` 로 사용
  - Chrome / Edge / Firefox 는 `*.localhost` 를 자동으로 127.0.0.1 로 연결하므로 hosts 파일 수정은 필요 없음
  - `.br`, `.dev`, `.app` 등 실제 도메인과 `.briefingroom` 같은 임의 최상위 도메인은 쓰지 않기로 함 (충돌 / hosts 등록 필요)
  - 포트 숨기기: 서버를 80번으로 직접 띄우면 브라우저가 포트를 생략함 (`http://lumia-briefingroom.localhost`). 추가 설치 없이 되고 보통 관리자 권한도 불필요
    - 80번이 이미 쓰이고 있으면(IIS, 백신, VPN, 다른 개발 서버 등) 자동으로 다른 포트로 넘어가고, 그 경우 포트가 붙은 주소를 화면에 안내하는 방식 검토
    - 대안(채택 안 함): 리버스 프록시(Caddy 등)는 프로그램이 하나 더 필요해 설치 간편화와 어긋남, `netsh portproxy` 는 관리자 권한 설정이 PC마다 필요
    - origin 이 고정되므로 `ui.port=auto` 때문에 볼륨 설정이 초기화되던 문제도 함께 줄어듦. SPEC §7.7 `ui.port` 와의 관계를 문서에서 정리
  - 앱 시작 시 브라우저가 이 주소로 열리게 할지, README 실행 방법에 어떻게 안내할지 문서에서 정하기
  - origin 이 바뀌므로 localStorage(볼륨 등)는 새 주소에서 처음엔 비어 있음. 문서에 명시

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
