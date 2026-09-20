# 루미아 브리핑룸 (Lumia Briefing Room)

이터널 리턴 교전 클립 자동 추출기. 설계 문서는 [docs/](docs/) 에 있다.

- [docs/SPEC.md](docs/SPEC.md) — 설계 결정과 근거
- [docs/research.md](docs/research.md) — 0단계 조사 결과(실측)
- [docs/plan.md](docs/plan.md) — 검출기 구현 계획 및 진행 상태
- [docs/plan-pipeline.md](docs/plan-pipeline.md) — 파이프라인 자동화(SPEC 2단계) 구현 계획 및 진행 상태
- [docs/plan-ui.md](docs/plan-ui.md) — 열람 UI(SPEC 3단계) 구현 계획 및 진행 상태

## 개발 환경

**반드시 가상환경을 쓴다.** 시스템 파이썬에 직접 설치하지 말 것 — 이 PC에는 다른 프로젝트(ultralytics 등)가 이미 깔려 있어 의존성이 충돌한다.

```bash
python -m venv .venv
.venv\Scripts\activate          # PowerShell/cmd
# 또는: source .venv/Scripts/activate   # git bash

pip install -e ".[dev]"
```

## 테스트

```bash
pytest
```

ffmpeg 를 찾을 수 없으면 ffmpeg 통합 테스트는 자동으로 skip 된다(제품 코드 실행에는 ffmpeg 가 필수지만, 순수 로직 테스트는 ffmpeg 없이도 전부 돈다). ffmpeg 위치를 지정하려면:

```bash
export LUMIA_FFMPEG=/path/to/ffmpeg.exe   # git bash
$env:LUMIA_FFMPEG = "C:\path\to\ffmpeg.exe"   # PowerShell
```

## 검출기 CLI (개발용)

매치 하나(세션 폴더 + 시작/종료 UTC 시각)를 분석해 교전 구간을 JSON 으로 출력한다.

```bash
python -m lumia_briefing_room.cli.detect_match \
  "<세션 폴더>" "<시작 ISO>" "<종료 ISO>" \
  --ffmpeg "<ffmpeg 경로>" --hwaccel d3d11va \
  --k-templates data/templates/digits/2560x1440.npz
```

## 개발 도구 (tools/)

`scripts/probe/` 와 달리 실사용하며 계속 돌리는 도구다.

| 도구 | 용도 |
|---|---|
| `tools/collect_frames.py` | 라벨링용 프레임 수집 |
| `tools/label_combat.py` | 검출기 결과로 라벨 초안 생성 |
| `tools/build_templates.py` | 라벨셋 → 숫자 본보기(npz) |
| `tools/eval_detect.py` | 라벨셋 대비 검출 정확도 리포트 |

가상환경을 활성화한 상태에서 실행할 것.
