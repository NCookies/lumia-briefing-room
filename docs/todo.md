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
- [x] 접속 주소를 `lumia-briefingroom.localhost` 로, 포트는 80번 우선 → plan-ui.md §0·§4-3(확인 필요 4건), SPEC §7.7 `ui.port`
- [x] 보기 모드 추가(일자 타임라인) → plan-ui.md §0·§4-4(확인 필요 3건), SPEC §3 실사용 피드백 UI
- [x] 자르기 구간 여러 개(구간마다 별도 클립 분할, 겹침 금지, 원본은 휴지통) → plan-ui.md §0·§4-5(확인 필요 4건), SPEC §3 실사용 피드백 UI
- [x] 자동 업데이트 기능 → 이미 SPEC §6 v2 이후 후보·§7.11, plan-deploy.md D9 에 있음(새로 적은 것 없음)
- [x] terraform 으로 OCI 인프라 구축(도커, 파일 → 나중에 DB, MCP 조사) → 새 docs/plan-infra.md, plan-deploy.md §7-11, SPEC §7.11 수신처
- [x] 버전 이름 명시(화면에 현재 버전 표시) → plan-deploy.md D11
- [x] 첫 실행 동의 기본값 전부 꺼짐 → plan-deploy.md D12·D3·§5, SPEC §7.11 표(`update.check` 기본 선택을 켬 → 끔으로 변경)
- [x] 라벨 전송이 꺼져 있으면 라벨링 UI 숨김 + 라벨 메모 입력창 → plan-deploy.md D12·§7-7, SPEC §7.11(`labelNote`), plan-infra.md §7(서버 스키마)
- [x] 배포 자동화(Release 업로드 + 바이러스 검사) → plan-deploy.md D13(확인 필요 §7-16~19)
- [x] 자동 업데이트를 꺼도 수동 확인·업데이트 가능 (대화 중 추가) → plan-deploy.md D9·D12, SPEC §7.11
- [x] 진단 zip 첨부 대신 서버 전송 (대화 중 추가) → plan-deploy.md D14·D3·§7-11, plan-infra.md §3·§7, SPEC §7.11
- [x] 진단 전송용 클라이언트 고유 ID(표시용 짧은 ID, 대화 중 추가) → plan-deploy.md D14·§7-21, SPEC §7.11 `telemetry.installId`, plan-infra.md §3
