# 제3자 구성 요소 고지

루미아 브리핑룸 배포본에는 아래의 제3자 소프트웨어가 포함되어 있습니다.
각 구성 요소는 원저작자의 라이선스에 따릅니다.

> 이 문서는 조사 결과를 정리한 것이고 법률 검토가 아닙니다. 각 구성 요소의
> 라이선스 전문은 원 저장소에서 확인하세요.

## FFmpeg (LGPL v2.1 이상)

- 포함 파일: `_internal/vendor/ffmpeg/` 의 `ffmpeg.exe`, `ffprobe.exe`,
  `avcodec-*.dll`, `avformat-*.dll`, `avfilter-*.dll`, `avutil-*.dll`,
  `avdevice-*.dll`, `swresample-*.dll`, `swscale-*.dll`
- 라이선스 전문: 같은 폴더의 `LICENSE.txt`
- 홈페이지: <https://ffmpeg.org/>
- 소스 코드: <https://github.com/FFmpeg/FFmpeg>
- 사용한 빌드: BtbN/FFmpeg-Builds 의 `ffmpeg-master-latest-win64-lgpl-shared`
  (<https://github.com/BtbN/FFmpeg-Builds/releases>). 빌드 스크립트와 구성은
  <https://github.com/BtbN/FFmpeg-Builds> 에 공개되어 있습니다.
- **GPL 구성 요소(`--enable-gpl`, 예: libx264/libx265)는 포함하지 않습니다.**
  빌드 스크립트(`tools/fetch_ffmpeg.py`)가 `-version` 의 `configuration` 줄에
  `--enable-gpl`/`--enable-nonfree` 가 없는지 확인한 뒤에만 동봉합니다.
- 이 앱은 FFmpeg 라이브러리를 링크하지 않고, 위 실행 파일을 **별도 프로세스로
  실행**해서만 사용합니다. 동봉된 DLL 은 보통의 파일이므로 사용자가 같은 버전의
  다른 빌드로 교체할 수 있습니다.

## RapidOCR 과 OCR 모델

- RapidOCR (Apache-2.0) — <https://github.com/RapidAI/RapidOCR>
- 포함 모델: `_internal/rapidocr/models/` 의 PP-OCRv5 계열 인식 모델(한국어·중국어),
  PP-OCRv6 검출 모델, 방향 분류 모델. 원 모델은 PaddleOCR(Apache-2.0) 계열입니다
  — <https://github.com/PaddlePaddle/PaddleOCR>
- **확인 필요**: 개별 모델 파일의 재배포 조건은 별도로 확인해야 합니다
  (plan-deploy.md §7-3).

## 파이썬 패키지

| 패키지 | 버전 | 라이선스 |
|---|---|---|
| anyio | 4.15.1 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| colorlog | 6.12.0 | MIT |
| fastapi | 0.141.1 | MIT |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD 3-Clause |
| httpx | 0.28.1 | BSD 3-Clause |
| idna | 3.20 | BSD 3-Clause |
| numpy | 2.2.6 | BSD 3-Clause |
| omegaconf | 2.3.1 | BSD 3-Clause |
| onnxruntime | 1.23.2 | MIT |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 |
| pillow | 12.3.0 | MIT-CMU |
| pyclipper | 1.4.0 | MIT |
| pydantic | 2.13.5 | MIT |
| pystray | 0.19.5 | **LGPL v3** |
| pythonnet | 3.1.0 | MIT |
| pywebview | 6.2.1 | BSD 3-Clause |
| pyyaml | 6.0.3 | MIT |
| rapidocr | 3.9.2 | Apache-2.0 |
| requests | 2.34.2 | Apache-2.0 |
| shapely | 2.1.2 | BSD 3-Clause |
| six | 1.17.0 | MIT |
| starlette | 1.6.0 | BSD 3-Clause |
| tqdm | 4.70.1 | MPL-2.0 AND MIT |
| uvicorn | 0.53.0 | BSD 3-Clause |

- **pystray 는 LGPL v3** 입니다 — <https://github.com/moses-palmer/pystray>,
  라이선스 전문: <https://www.gnu.org/licenses/lgpl-3.0.html>.
  이 앱은 pystray 를 수정하지 않고 그대로 씁니다. 배포본에서는 PyInstaller 아카이브에
  묶지 않고 **`_internal/pystray/` 폴더에 소스 파일(.py) 그대로** 들어 있습니다
  (`tools/pyi_hooks/hook-pystray.py`). 이 폴더의 파일을 수정하거나 같은 이름의
  다른 버전(<https://pypi.org/project/pystray/>)으로 바꿔 넣으면 그 파일을 읽어
  실행합니다. 이 앱의 전체 소스와 빌드 스크립트(`tools/build_release.py`)가 공개되어
  있으므로 수정한 pystray 로 배포본을 다시 만들 수도 있습니다.

## Python 런타임

- CPython 3.10 (PSF License) — <https://www.python.org/>
- PyInstaller 부트로더 (GPL with bootloader exception — 생성물 배포에는
  제약이 없습니다) — <https://github.com/pyinstaller/pyinstaller>

## 앱 자체

- 소스 코드는 MIT 라이선스입니다(저장소 루트의 `LICENSE`).
- 배포본에는 게임 화면의 글자 모양을 학습해 만든 본보기 데이터(`_internal/data/templates/*.npz`, 숫자·지역명·일차 판독용 작은 조각)가
  들어 있습니다. 게임 화면 원본 이미지는 포함하지 않습니다. 이터널 리턴은 님블뉴런의 저작물이며,
  이 앱은 **비공식 팬 제작 도구로 님블뉴런과 관련이 없습니다.**
- 권리자의 삭제·시정 요청은 lumia.briefingroom@gmail.com 으로 받습니다.
