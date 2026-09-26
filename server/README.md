# 수신 서버 (server/receiver)

앱이 보내는 라벨·오류 로그·진단 번들을 받아 저장하는 FastAPI 서버다. **이 서버의 애플리케이션 코드와 전송 계약(`contract/`)은 이 저장소가 갖는다**(앱과 함께 바뀌므로).
서버를 띄우는 인프라(OCI VM·Terraform·compose·Caddy·watchtower·DNS)와 운영 명령은 별도 **infra 저장소**에 있다.

- 코드: [receiver/](receiver/) (`app/`, `tests/`, `Dockerfile`)
- 계약(요청·응답 명세와 픽스처): [../contract/](../contract/)
- 앱 쪽 연결 계획·결정: [../docs/plan-infra.md](../docs/plan-infra.md)

## 이미지 빌드와 배포

`server/receiver/**`·`contract/**`·`.github/workflows/receiver.yml` 이 main 에 push 되면 [receiver 워크플로](../.github/workflows/receiver.yml) 가 테스트를 돌리고 `ghcr.io/<소유자>/receiver:latest`(amd64·arm64)를 올린다. 서버의 watchtower 가 이 이미지를 주기적으로 받아 receiver 컨테이너만 교체한다(compose·`.env`·간격은 infra 저장소). 이미지 이름은 이 저장소로 옮기기 전과 같다.

**처음 한 번(저장소를 옮긴 뒤)**: GitHub 의 패키지 `receiver` → Package settings → "Manage Actions access" 에 이 저장소를 Write 로 추가해야 이 저장소의 워크플로가 같은 이름의 이미지를 올릴 수 있다(패키지는 계속 public 이어야 서버가 인증 없이 받는다).

## 수신 API

모든 `/v1/*` 는 `X-Api-Token` 헤더 필요(`receiver_api_token`, 여러 개 가능 — 위 "API 토큰 교체"). 허용 목록에 없는 필드는 버린다(버려진 필드 **이름**만 일별 집계에 센다). `installId` 는 UUID, 모든 페이로드에 `schemaVersion`·`mode`(`dev`/`release`)가 필요하다. `/docs` 등 API 문서는 꺼져 있다(404).

**요청·응답 명세의 원본은 [`contract/receiver.schema.json`](../contract/receiver.schema.json)** 이고, `contract/fixtures/` 의 수락·거부·버림 예시를 서버 테스트(`server/receiver/tests/test_contract.py`)와 앱 테스트(`tests/test_contract.py`)가 같이 쓴다. 필드를 바꿀 때는 스키마·`app/schemas.py`·픽스처를 함께 고친다(어긋나면 테스트가 깨진다).

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/healthz` | 상태 확인(토큰 불필요) |
| POST | `/v1/labels` | 라벨 묶음 → `data/labels/<installId>/<clipKey>.json` (같은 `clipKey` 를 다시 보내면 덮어씀) → `{saved}` |
| POST | `/v1/logs` | 오류 로그·환경 → `data/logs/<installId>/<날짜>.jsonl` → `{saved}` |
| POST | `/v1/diagnostics` | 진단 번들(사용자가 버튼으로 보냄) → `data/diagnostics/<installId>/<접수번호>.json` → `{receiptId:"R-20260925-K7M3QX", saved}` |
| GET | `/v1/admin/labels` | **관리자 전용** 라벨 내보내기(`X-Admin-Token`, 업로드 토큰으로는 안 됨). `mode`(dev/release)·`after`(이전 응답의 `next`)·`limit`(최대 2000). `ADMIN_TOKEN` 이 비어 있으면 404. `tools/pull_labels.py` 와 앱의 관리자 탭이 쓴다. |
| GET | `/v1/admin/status` | **관리자 전용** 서버 상태: 모드별(release/dev) 라벨·로그 파일·진단 수·설치 수·종류별 마지막 수신 시각, 오늘 요청·거부 건수(엔드포인트별), 디스크 사용률·데이터 용량, 지금 차단 중인 IP **개수**(주소는 안 줌), 보관 기간 |
| GET | `/v1/admin/diagnostics` | **관리자 전용** 진단 번들 목록(최신순). `mode`·`q`(접수 번호·표시용 ID·installId 앞부분)·`limit`(최대 500)·`offset`. 항목은 요약(접수 번호·표시용 ID·installId·수신 시각·버전·OS·항목 수·오류 수) |
| GET | `/v1/admin/diagnostics/{receiptId}` | **관리자 전용** 진단 번들 전문(환경 정보·로그 발췌). 접수 번호 형식이 아니면 404 |
| GET | `/v1/admin/logs` | **관리자 전용** 오류 로그 항목을 펼쳐 최신순으로. `mode`·`installId`·`level`·`q`(메시지·예외 종류)·`limit`(최대 1000)·`offset` |
| GET | `/v1/admin/logs/groups` | **관리자 전용** 같은 오류 묶음 집계(`fingerprint`, 없으면 예외 종류+메시지): 횟수·설치 수·처음/마지막 시각·대표 메시지, 많은 순 |
| DELETE | `/v1/installs/{installId}` | 그 설치가 보낸 라벨·로그·진단(개발 모드 포함) 전부 삭제 |

**보관과 삭제**: 로그·진단 파일은 수신 후 `RETENTION_DAYS`(기본 90)일이 지나면 서버가 하루 한 번(그리고 시작할 때) 자동 삭제한다. 라벨은 삭제 요청 전까지 보관한다. [`docs/privacy.md`](../docs/privacy.md) 에 적은 보관 기간과 이 값이 같아야 한다.

**IP 를 남기지 않는 설정**: caddy 는 **전역** `log { exclude http.log.access }` 로 접근 로그를 어디에도 남기지 않고(사이트 블록의 `log { output discard }` 만으로는 서버 IP 로 직접 접속한 요청이 로그에 남는다 — 2026-09-25 발견·수정), receiver 는 uvicorn `--no-access-log` 로 실행한다. 확인 방법: 서버 IP 로 `curl http://<공인 IP>/` 를 보낸 뒤 `docker compose logs caddy | grep -c http.log.access` 가 0 인지 본다. 컨테이너 로그는 크기 회전(5MB×2)만 하며, 오류 로그에 IP 가 찍히는지는 배포 후 `docker compose logs` 로 확인한다.

**요청 제한·차단·알림**: `/v1/*` 요청을 클라이언트 IP(caddy 가 붙인 `X-Forwarded-For` 의 마지막 값) 별로 세어, 10분 창에서 요청이 `RATE_LIMIT_REQUESTS`(기본 60)회를 넘거나 거부되는 요청(401·404·405·413·422)이 `RATE_LIMIT_FAILURES`(기본 15)회 쌓이면 그 IP 를 `BLOCK_SEC`(기본 3600)초 동안 차단한다(429 + `Retry-After`). `/healthz` 는 제외. 정상 앱은 하루 1회 소량만 보내므로 임계값은 넉넉하다. **IP 는 receiver 프로세스 메모리에만 있고 디스크에 쓰지 않으며 재시작하면 사라진다.** 차단이 생기면 `DISCORD_WEBHOOK_URL` 로 알린다(IP 는 앞 두 자리만, 시간당 최대 10건). 웹훅 URL 은 비밀 값이라 서버 `.env` 와 로컬 `terraform.tfvars`(`discord_webhook_url`)에만 두고 저장소에 넣지 않는다. 비워 두면 알림 없이 차단만 한다. 한계: IP 기준이라 VPN 으로 우회할 수 있고, 같은 공유기 뒤 사용자는 한 IP 로 보인다.

**일별 집계**(`data/stats/<날짜>.json`): 엔드포인트별 수신 건수·총/평균 바이트, 거부(422)된 요청 수와 거부 사유가 된 필드 이름, 허용 목록 밖이라 버린 필드 이름. 값(라벨 메모 포함)은 남기지 않는다. 앱과 서버 스키마가 어긋났는지, DB 가 필요한 규모인지 보는 자료다.

요청 본문 상한 20MB(`MAX_BODY_BYTES`, Caddy 는 21MB). 라벨 필드는 2026-09-25 에 앱의 실제 메타데이터(`ClipMetadata`)와 하나씩 대조해 확정했다(전송·제외 분류는 `contract/app-metadata-fields.json`).

로컬 개발/테스트:

```
cd server/receiver
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest
```

2026-09-25 (계약 변경 전) 실서버 확인: 토큰 없음 → 401, 라벨 업로드(허용 밖 `nickname` 포함) → `{"saved":1}` 이며 허용 밖 필드는 버려짐, `installId` 삭제 → `{"deleted":true}`, `/docs` → 404.

2026-09-25 계약 확장 배포 후 실서버 확인(읽기 전용, 데이터를 쓰는 요청은 하지 않음): 토큰 없는 `POST /v1/diagnostics`·`/v1/labels`·`DELETE /v1/installs/…` → 401, `/docs` → 404, `/healthz` → 200. 배포 방법: main push → Actions 가 이미지 갱신, 설정 파일(infra 저장소의 `deploy/`)은 서버의 `/opt/infra` 에 직접 반영(`scp` 로 `docker-compose.yml`·`Caddyfile` 올리고 `caddy validate` 로 문법 확인 → 옛 파일은 `*.bak` 으로 백업 → `.env` 에 새 변수 추가 → `docker compose pull receiver && docker compose up -d`). `.env` 는 root 소유 0600 이라 서버에서 읽거나 고칠 때 `sudo` 가 필요하다.
