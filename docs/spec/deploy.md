# 배포·업데이트·데이터 전송·수신 서버

> 목표: 파이썬·node·ffmpeg 가 없는 PC 에서 설치 파일 하나로 동작, 공개 배포는 GitHub Releases(`NCookies/lumia-briefing-room`, 공개 저장소). 빌드·릴리스 절차는 [DEVELOPMENT.md](../DEVELOPMENT.md), 릴리스 전 실측은 [release-checklist.md](../release-checklist.md), 개인정보 안내는 [privacy.md](../privacy.md).

## 1. 원칙

- **핵심 기능(검출·클립·열람)은 네트워크 없이 동작한다.** 네트워크는 **사용자가 동의한 부가 기능**(업데이트 확인, 라벨·오류 로그 전송)과 **사용자가 직접 누른 동작**(수동 업데이트 확인·설치, 진단 정보 보내기)에만 쓰고, 꺼져 있거나 실패해도 핵심 기능은 영향이 없다.
- **영상·썸네일·결과표 이미지·화면 조각·닉네임·팀원 정보·경로 원문은 어떤 경우에도 보내지 않는다.**
- 안티치트 안전: 게임 프로세스(메모리·입력·패킷)를 건드리지 않고 스팀이 저장한 파일과 `Player.log` 만 읽는다.

## 2. 패키징

### 리소스·버전·경로

- 리소스(프로필 JSON, `data/templates/*/*.npz`, 프론트 `dist`, ffmpeg, OCR 모델)는 `paths.resource_dir()` 한 곳에서 찾는다(개발 = 저장소 루트, 빌드본 = `sys._MEIPASS`). 본보기 누락은 경고.
- 버전은 `lumia_briefing_room.__version__` 한 곳(pyproject 동적 버전, 설치기, `GET /api/app-info`, 태그).
- 설정·로그·상태는 `%LOCALAPPDATA%\LumiaBriefingRoom\`(설정 파일은 `%APPDATA%\LumiaBriefingRoom\config.json`), 클립은 `%USERPROFILE%\Videos\LumiaBriefingRoom\`. 설치 폴더에 쓰지 않는다.

### ffmpeg (필수 번들)

- 탐색: `LUMIA_FFMPEG` → 번들 `vendor/ffmpeg` → `PATH`. ffprobe 도 같이.
- **LGPL 빌드만 번들**(BtbN `lgpl` shared, 149MB). 인코딩은 H.264 프록시뿐이라 LGPL 인코더 `h264_mf`(소프트웨어 MFT, 1080p 8Mbps 비트레이트 모드)를 쓰고, 없으면 `libx264`(개발 PC 의 GPL 빌드)로 넘어간다. 하드웨어 인코더(`amf`/`nvenc`/`qsv`)는 기기 의존이라 채택 안 함.
- 모든 subprocess 는 `procs.py`: `CREATE_NO_WINDOW`, BELOW_NORMAL, 작업 개체(앱 종료 시 자식 종료).

### 프록시 (`pipeline/proxy.py`)

- HEVC 를 못 트는 PC 에서 클립별로 **처음 재생하려 할 때** 만든다(1080p, 키프레임 1초). 위치는 영상 드라이브의 캐시 폴더(`resolve_paths().proxy_cache` — 옛 경로 모드는 `<스팀 클립 폴더>/.proxy`, 새 구조는 `<저장 폴더>/.cache/proxy`), VOD 클립도 같은 폴더. 자르기 뒤엔 mtime 으로 무효 판정, 고아 프록시는 삭제·자동 정리 때 쓸어 낸다. 90초 클립 ≈ 30초.

### PyInstaller `--onedir` + Inno Setup

- `--onefile` 은 느리고 오탐이 심해 `--onedir`. `--noconsole`: 파일 로그만 쓰고 `sys.excepthook`·`threading.excepthook` 으로 예외를 파일에 남긴다. 시작 실패는 메시지 상자.
- 번들에는 `templates/*/*.npz` 와 프로필만 넣는다. `verify_bundle` 이 `_samples`·`*_labels.jsonl` 이 들어가면 실패시킨다. rapidocr 는 실제로 여는 모델 4개만(안 쓰는 `PP-OCRv6_rec_small`·opencv videoio DLL 제외) → 약 400MB.
- pystray(LGPL v3)는 `tools/pyi_hooks/hook-pystray.py` 로 `_internal/pystray/*.py` 로 풀어 교체 가능하게 한다.
- `--selftest`: 번들 리소스·OCR·ffmpeg·프록시 인코더 등 점검.
- 설치기(`installer/lumia.iss`): 사용자 영역(`%LOCALAPPDATA%\Programs\LumiaBriefingRoom`, 관리자 권한 없음), 설치 직후 `--open-ui` 로 앱을 띄우고 마침 화면에 안내, 트레이 알림. 제거 시 자동 시작 값 삭제·실행 중 앱 종료·설정 삭제 여부 질문(무인 제거는 묻지 않음)·**클립 폴더는 남김**. `THIRD_PARTY_NOTICES` 동봉. 조용한 설치일 때 진행 창을 최상위로 올린다(`ShowProgressOnTop`). `/RELAUNCH=1` 이면 설치 뒤 앱을 `--start-server` 로 다시 띄운다.
- 코드 서명 없음 → SmartScreen 경고(안내로 대응). Windows Defender 가 `Wacatac.C!ml`(머신러닝 추정)로 격리한 사례가 있어 README 에 허용 방법을 적었다.

### 함정 (빌드본에서만 드러나는 것)

- `--noconsole` 이면 `sys.stdout` 이 `None` → uvicorn 기본 로깅이 `isatty()` 에서 죽는다 → `uvicorn.Config(log_config=None)`. 트레이는 멀쩡하고 UI 만 안 열려 찾기 어렵다.
- 콘솔 없는 동작 재현은 `pythonw` 로 부족하고 `DETACHED_PROCESS` 가 필요하다.
- PyInstaller 가 `--add-data` 안의 `.dll` 을 바이너리로 한 벌 더 복사한다 → ffmpeg 는 빌드 뒤 직접 복사.
- `vendor/ffmpeg`(LGPL)가 있으면 테스트 픽스처(`libx264` 필요)가 깨진다 → `tests/conftest.py` 가 테스트에서만 PATH 의 전체 빌드를 지정.
- Inno Setup 을 winget 으로 넣으면 사용자 영역에 깔린다. 무인 제거의 `MsgBox` 는 멈춘다(`UninstallSilent` 확인).
- `dist` 안에 셸이 들어가 있으면 지울 수 없다. 앱이 실행 중이면 뮤텍스 때문에 빌드본을 못 띄운다.
- 셸 heredoc 로 백슬래시가 든 파일(`.iss`·`.wsb`·파이썬)을 쓰면 백슬래시가 줄어든다 — Write 도구로 쓰고 확인한다.
- pytest 는 모듈 이름 `setup`·변수 `setup_module` 을 nose 훅으로 취급한다(그래서 첫 실행 API 는 `api/onboarding.py`).

## 3. 첫 실행 화면과 동의

- `consent.version` 이 현재 버전(3)보다 낮으면 앱이 UI 를 자동으로 열어 첫 실행 화면을 띄운다. **설치기에서는 묻지 않는다**(한 곳에서만).
- 순서: 스팀 녹화 폴더(자동 탐지/직접 고르기, 배경 녹화 켜는 법, 클립 폴더) → 녹화 해상도 지원 여부(측정 / 16:9 축척 / 비율 다름 — 진행은 막지 않음) → 선택 기능 세 개 → "과거 녹화도 분석하기"(녹화 폴더와 ffmpeg 가 있을 때만, 기본 선택).
- 선택 기능 **업데이트 확인·라벨 전송·오류 로그 전송은 모두 기본 꺼짐**(사용자가 직접 켠다). 창을 그냥 닫으면 꺼진 채 두고 다음 실행에 다시 묻는다. 보내는 항목이 늘면 버전을 올려 **새 항목만** 다시 묻는다(1=setup, 2=update, 3=labels·logs).
- 옵션 "정보·진단" 의 "선택 기능" 에서 언제든 바꾼다.

## 4. 자동 업데이트 (`updater.py`, `api/update_routes.py`)

- 확인: `GET https://api.github.com/repos/NCookies/lumia-briefing-room/releases/latest`(초안·사전 릴리스 제외), 태그 `vX.Y.Z` 숫자 비교. 설치기(`*-setup.exe`)와 같은 이름의 `.sha256` 이 없거나 주소가 이 저장소 릴리스가 아니면 제공하지 않는다.
- 자동: `update.check` 가 켜져 있을 때만 시작 후·하루 1회(`update_state.json` 에 마지막 확인, 실패 시 1시간 뒤). 꺼져 있으면 네트워크 0회(30초마다 설정만 읽어 켜면 곧 동작). 새 버전은 버전당 한 번 트레이 알림.
- 수동: 옵션 "업데이트 확인"(`POST /api/update/check`) → "업데이트". `update.check` 와 무관. 화면 위 배너와 제목 옆 "⬆ 새 버전" 은 어느 경로로든 새 버전을 알면 뜬다. 상태는 `UpdateProvider` 가 화면 전체에서 공유.
- 설치(`POST /api/update/install`): `%LOCALAPPDATA%\LumiaBriefingRoom\updates\` 에 `.part` 로 받으며 SHA-256 계산 → **`.sha256` 과 다르면 지우고 실행하지 않는다**(서명 없는 배포의 유일한 무결성 확인) → 앱을 **먼저 종료한 뒤** `/SILENT /SUPPRESSMSGBOXES /NORESTART /RELAUNCH=1` 로 설치기 실행(`cli/app.py::DeferredInstaller`). 개발 모드(비 exe)는 실행하지 않는다.
  - 설치기는 실행 중인 앱(`AppMutex`)을 보면 조용한 모드에서 바로 중단한다 — 앱이 살아 있을 때 띄우면 **겉으로 성공처럼 보이고 실제로는 설치되지 않는다**(0.1.4 실사고. 0.1.4 앱은 버튼으로 못 올라가 0.1.5 를 직접 설치해야 했다).
  - 앱의 작업 개체가 설치기까지 죽이지 않게 `BREAKAWAY_OK` + `CREATE_BREAKAWAY_FROM_JOB`.
  - 설치기가 앱을 `--start-server` 로 다시 띄워 열려 있던 탭이 자동 새로고침된다. 8초 안에 탭 요청이 없으면 브라우저를 직접 연다. `pendingUpdate` 를 남겨 새 버전이 뜨면 "업데이트가 완료되었습니다 vA → vB" 창을 한 번(`POST /api/update/ack`).
- 로컬 시험: `tools/fake_release_server.py` + `LUMIA_UPDATE_API_URL`·`LUMIA_UPDATE_DOWNLOAD_PREFIX`(둘 다 루프백일 때만 적용) — [DEVELOPMENT.md](../DEVELOPMENT.md).

## 5. 라벨·오류 로그 전송 (`telemetry/`)

| 파일 | 역할 |
|---|---|
| `payload.py` | 메타데이터 → 계약 `Label`(변환·길이 정리·키 해시·표시용 ID) |
| `collect.py` | 스팀·VOD 클립과 `.labels/` 보관소에서 라벨 수집 |
| `outbox.py`·`scrub.py` | ERROR 이상 로그를 구조화 핸들러로 outbox(`outbox\errors.jsonl`, 20MB)에, 개인정보 제거·오류 지문 |
| `environment.py`·`runtime_stats.py` | 환경 정보, 판독 실패 통계, 프록시 인코더·시간, 분석 시간 비율, hwaccel, HEVC 재생 여부 |
| `client.py`·`sender.py` | 전송·재시도 분류, 하루 1회·백오프·동의/모드 게이트·미리보기·삭제 요청 |
| `endpoint.py`·`state.py` | 서버 주소·토큰(설정 → 환경변수 → 번들), 진행 상태 |

- 종류별 하루 1회 묶음(각 200개). 실패하면 15분부터 2배씩 최대 6시간 백오프(Retry-After 가 길면 따름). **413·422 는 재시도해도 같아 그 묶음을 버리고**, 401·5xx·타임아웃은 미룬다. 앱은 절대 멈추지 않는다. 동의가 꺼져 있으면 네트워크 0회.
- 라벨: `userLabel` 있는 클립만, **전송 때만** `pvp→combat`, `pve→other`(로컬 값·보관소·평가 도구는 그대로). 클립 키는 설치 ID 를 소금으로 한 해시(`matchKey`·`clipKey`, 32자 hex) — 경로·시각 원문은 안 나간다. 내용 지문이 바뀔 때만 다시 보내 서버가 덮어쓴다. VOD 라벨도 보낸다(`source`, 스트리머·파일은 안 보냄). `labeledAt` 은 라벨 값이 바뀔 때만 기록. `pvpSignalValues` 는 아직 수집하지 않는다.
- 보내지 않는 메타 필드(`contract/app-metadata-fields.json` 의 `excluded`): `title`, `sessionDir`, 각종 UTC 시각·세그먼트 번호·`videoOffsetSec`, 경로들, `pinned`, `teamCharacters`, `matchResult`(닉네임·팀원 포함). 앱 테스트가 메타데이터의 **모든 필드**를 sent/변환/excluded 로 분류했는지 대조한다.
- 개발 모드는 기본 전송 안 함, `telemetry.allowDevSend` 일 때만 `mode=dev`(서버가 따로 저장).
- 서버 주소·토큰은 코드에 없다. 빌드 때 환경변수(GitHub Secrets `LUMIA_RECEIVER_URL`·`LUMIA_RECEIVER_TOKEN`)로 번들에 주입. 없으면 "서버 전송이 꺼진 빌드".
- **토큰은 공개 키 수준으로 본다**(설치기에서 꺼낼 수 있다). 실질 방어는 서버의 요청 제한·차단·알림이다. 서버는 여러 토큰을 동시에 허용한다.
- 옵션 "정보·진단": 전송 상태, **미리보기**(개인정보 제거 후, 네트워크 안 씀), **보낸 데이터 삭제 요청**(서버의 내 라벨·로그·진단을 지우고 전송을 끔).
- 개인정보 제거 회귀 테스트(`tests/test_telemetry_scrub.py`)는 실제 로그 구조를 본뜬 가짜 샘플로 닉네임·사용자 이름·절대/UNC/POSIX 경로를 검증한다.

## 6. 진단 정보 보내기

- 옵션 "진단 정보 보내기" → 미리보기(최근 오류 100건 — 정기 전송과 분리된 `errors_recent.jsonl` 1MB, 환경 정보, 판독 실패 통계) → 확인 → 접수 번호(`R-날짜-6자`) 표시·저장. `telemetry.sendLogs` 와 무관한 1회성, 자동 전송을 켜지 않는다.
- 표시용 ID `LUMIA-XXXX-XXXX`(설치 ID 에서 파생, 복사 버튼, "알리면 본인과 연결될 수 있다" 안내, 재설치하면 바뀜). **삭제 요청은 전체 설치 ID 로만**(짧은 ID 는 남이 알 수 있다).
- 실패하면(오프라인·서버 오류·서버 정보 없는 빌드) zip 으로 저장해 보내 달라고 안내. **zip 내보내기는 대안으로 유지**(닉네임·사용자 이름 제거, `info.json` 에 표시용 ID, 토큰 제외).

## 7. 릴리스 자동화 (`.github/workflows/release.yml`)

- `v*` 태그 푸시 → `check-tag`(태그 = `__version__`, CHANGELOG 절 존재 — **패치노트 없는 릴리스를 첫 단계에서 막는다**) → 빌드(ffmpeg·OCR 모델·배포본·설치기) → `.sha256` → `gh release create --draft` → VirusTotal 업로드(API 직접 호출, 실패해도 계속) → 본문에 검사 링크 → 공개. 초안으로 만들었다가 마지막에 공개하므로 반쯤 올라간 릴리스가 보이지 않는다. 약 4분.
- `workflow_dispatch` 는 빌드만 하고 아티팩트(3일).
- Secrets: `LUMIA_RECEIVER_URL`, `LUMIA_RECEIVER_TOKEN`, `VT_API_KEY`.
- 패치노트 원본은 루트 `CHANGELOG.md`(`## [x.y.z] - 날짜`, `새로 생겼어요`/`좋아졌어요`/`고쳤어요`, 화면에서 보이는 변화 위주 — 커밋 메시지 자동 생성은 쓰지 않는다). 앱 안(옵션 → 정보·진단)과 Release 본문 양쪽에 쓰인다.
- **태그를 만들기 전에 [release-checklist.md](../release-checklist.md) 의 미확인 실측 항목을 확인한다**(CLAUDE.md).

## 8. 설치·사용자 수 통계 — 만들지 않는다 (2026-09-27)

새 동의 항목·사용 신호(`POST /v1/ping`)는 만들지 않는다. 필요하면 GitHub Release `download_count`(업데이트도 세어짐, 직접 전달본은 안 세어짐)와 서버가 이미 받는 서로 다른 `installId` 수(동의자만, 하한)를 본다.

## 9. 수신 서버

- **코드는 이 저장소**: `server/receiver/`(FastAPI), 계약 `contract/receiver.schema.json` + `contract/fixtures/`(앱 `tests/test_contract.py` 와 서버 테스트가 같은 파일을 쓴다 — 한쪽만 고치면 깨진다), CI `.github/workflows/receiver.yml`. 운영·배포는 [server/README.md](../../server/README.md).
- **인프라는 별도 저장소 `infra`**(Terraform·compose·Caddy·watchtower·DNS). OCI `VM.Standard.E2.1.Micro`(A1 은 `LaunchInstance` 404 로 실패), 메모리 1GB, Terraform 상태는 로컬 파일, 도메인 → Caddy Let's Encrypt, 이미지 ghcr + watchtower(2시간).
- API: `POST /v1/labels`·`/v1/logs`·`/v1/diagnostics`(접수 번호), `DELETE /v1/installs/{installId}`, 인증 `X-Api-Token`, 본문 20MB 상한.
- 관리자: `GET /v1/admin/labels`(증분 커서, dev/release 분리)·`status`·`diagnostics`·`logs`·`logs/groups`, `X-Admin-Token`(`ADMIN_TOKEN` 이 비면 404). 로컬로 가져오기 `tools/pull_labels.py`(→ `.labels/` 형태). 개발 모드 앱의 "관리자" 탭(`api/admin_routes.py`)이 관리자 토큰을 브라우저에 넘기지 않고 대신 호출한다(배포 모드 404).
- 남용 방어: IP 별 메모리 제한(기본 10분에 60회, 거부 15회 → 1시간 차단, 429), Discord 알림(IP 앞 두 자리, 시간당 10건), 올바른 관리자 토큰은 제한 제외. IP 는 디스크에 안 쓴다.
- 개인정보: 접근 로그 IP 비활성(Caddy 전역 `log { exclude http.log.access }` — 서버 IP 로 직접 접속한 요청도), 로그·진단 90일 자동 삭제, 라벨은 삭제 요청 전까지. 서버 오류 기록의 IP 는 "남을 수 있고 크기 기준으로 순환" 으로만 약속.
- 저장은 파일(라벨 건당 JSON, 로그 JSONL). DB 는 데이터가 쌓여 조건 조회가 불편해질 때 정한다.

## 10. 라이선스·게임사 지침 (2026-09-25 판단, 법률 검토 아님)

- 앱 **MIT**(소스에만, 게임 자산 제외 명시). pystray·ffmpeg 는 LGPL 고지(`THIRD_PARTY_NOTICES`).
- 게임사(님블뉴런) IP 정책·EULA·운영 정책에 도구에 대한 명시적 금지는 없다. 지키는 것: 게임 화면 이미지(`_samples`)를 저장소·이력·번들에서 제거(`git filter-repo` 로 이력 정리, 개인정보·경로·닉네임 치환 완료), "비공식 팬 제작 도구, 님블뉴런과 무관" 고지, 공식 로고·UI 이미지 미사용(앱 아이콘은 `icon.py` 가 그린다). 사전 문의는 하지 않았고 요청이 오면 바로 응한다(README 연락처).
- 본보기 `.npz` 는 원본 화면이 아니고 실행에 필수라 포함한다. 문제 제기 시 제거하고 `tools/build_templates.py` 로 사용자가 만들게 한다.
- VirusTotal 에는 공개 저장소 릴리스만 올린다.
