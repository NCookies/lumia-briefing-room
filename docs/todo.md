# TODO 입력함

> 사용자가 자유롭게 적는 입력 전용 파일이다. `/todo-sync` 세션이 이 파일을 읽고
> 문서(SPEC / plan*.md / README)에 반영한다. **코드는 건드리지 않는다.**
>
> 형식: `- [ ] 내용` 한 줄이 한 항목. 보충 설명은 들여쓴 하위 줄에 적는다.

## 당장 구현

## 추후 구현

## 처리됨

<!-- /todo-sync 가 반영을 끝낸 항목을 "- [x] 내용 → 반영한 문서 §절" 형태로 옮긴다. -->

- [x] 패치노트 작성 → 루트 `CHANGELOG.md`(버전별 사용자용 절, 릴리스 본문으로 자동 사용), plan-deploy.md D13
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
- [x] 탭 이름 변경(내 녹화 → 스팀 녹화, 다시보기 → 영상 파일) → plan-ui.md §0, SPEC §2.14 머리
- [x] 빈 목록 안내 화면(가운데 정렬, 과거 녹화 분석 버튼, 영상 경로 추가 버튼) → plan-ui.md §0
- [x] 영상 파일 이름 구분(클립 유니크 ID `clipUid`, 파일 이름은 유지) → plan-ui.md §0·§4-6, SPEC 클립 메타데이터, plan-deploy.md §5, plan-infra.md §7
- [x] 관리자 전용 대시보드(로컬 실행 전용, 추후) → plan-infra.md §8
- [x] 영상 파일 탭 지원 확장자 `(?)` 도움말 (대화 중 추가) → plan-ui.md §0·§4-6, SPEC §2.14 머리
- [x] 과거 녹화 분석 진행률이 50% 로 한 번에 뛰는 문제 → plan-backfill.md §0 B8·§7, roadmap.md P4
- [x] 영상 파일 분석 후 원본 삭제 옵션(묻기/항상/안 함, 휴지통·영구 삭제 선택, 기본 휴지통) → plan-vod.md V7·§8-10·§2.1, SPEC §7.10·§7.8·§2.14
- [x] 프로그램 설치 통계 → plan-deploy.md D15(**현 상태 유지**, 새 동의 항목 만들지 않음 — 대화 중 결정)
- [x] dak.gg 파싱으로 내·팀원 캐릭터 읽기(추후 구현으로 기록, 조건·확인 필요만 정리) → plan-ui.md §7, SPEC §6 v2 이후 후보
- [x] 코발트 프로토콜 지원 → plan.md §10(C0~C5), SPEC §2.9, roadmap.md P4
- [x] 앱 휴지통 제거, 삭제 확인 창(다시 묻지 않기 / 영구 삭제하기 체크박스, 옵션에서도 설정) (대화 중 추가) → plan-ui.md §0·§4-7, plan-vod.md §8-10, SPEC §1·§7.6·§7.7, roadmap.md P4
- [x] 휴지통 복원 시 파일 함께 복원 안내(삭제 확인 창에 명시)·자동 정리 기본 영구 삭제·삭제 예정 미리 표시(빨간 계열)·휴지통 못 쓰는 드라이브는 앱이 처리하지 않음 (대화 중 추가) → plan-ui.md §0·§4-7, plan-vod.md V7, SPEC §7.6·§7.7
- [x] 삭제 예정 표시는 클립이 갱신될 때 한 번 계산(정확하게), 자동 정리 켤 때 경고, Windows 휴지통 구현은 추천대로(`Send2Trash`) (대화 중 추가) → plan-ui.md §0·§4-7, plan-vod.md §8-10, SPEC §7.6
- [x] (커뮤니티 피드백 2026-09-27) 풀 영상 탭·클립 제목 검색·일자 타임라인 시점 추정·영상 파일 날짜별 보기, 태그 필터 작동 의심은 재현 확인 필요 → plan-ui.md §0·§4-8·§4-9, plan-vod.md V8·§8-11, SPEC §7.12, roadmap.md P4
- [x] 캐릭터 선택창 초상화 캡처로 팀원 캐릭터 표시(이름 인식 대안) → plan-ui.md §0, SPEC §2.10
- [x] 교전 점수 필터 "0% 이상" 옵션 삭제 → plan-ui.md §0
- [x] 카드/일자 타임라인 보기 모드 토글에 라벨 표시 → plan-ui.md §0
- [x] 자동정리를 스팀 녹화/영상 파일/풀영상 분류별로 설정 + 분류별 클립 총 용량 표시 → plan-ui.md §0, SPEC §7.6·§7.10, plan-vod.md §8-6
- [x] 페이즈 인식 6~7일차까지 규칙성 확인, 시점 미상 클립 원본 영상 순서 정렬 폴백 → plan-ui.md §4-8
- [x] 풀영상 기능: 클립 플레이어에 "풀영상 보러가기" 버튼 추가(처음 범위에 포함) → plan-ui.md §0 (풀 영상 탭 항목 (4))
- [x] 방향키를 클립 이동 대신 클립 내 -5/+5초 탐색으로 변경 → plan-ui.md §0
- [x] 다시 분석 중인 게임 항목이 잘 보이게 진행 애니메이션 등 추가(스팀 녹화 vs 영상 파일 탭 UI 불일치, 2026-09-28 재확인 — 이미 구현·충분하다고 확인) → plan-ui.md §0 (`work/plan-followup` 브랜치에 구현, main 병합 대기 중)
- [x] 라벨링 했을 때 다음 영상으로 자동으로 넘어가지 않게 하기(개발 모드도 포함하도록 기존 결정 변경) → plan-ui.md §0 "라벨링 자동 다음 이동 제거 — 개발 모드도 포함" (`work/plan-followup` 브랜치, 설계만 반영·미구현)
- [x] 게임별 풀영상 + 재생바에 교전 추정 구간 하이라이트(클릭해서 클립 저장) → plan-ui.md §0 "풀 영상 탭" (4), SPEC §7.12 (기존 풀 영상 탭 계획에 기능 추가, 클립 자동 추출 파이프라인 재설계는 아님, `work/plan-followup` 브랜치, 설계만 반영·미구현)
