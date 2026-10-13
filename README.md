# AFP Designer

시드 부동 단백질(AFP)에서 후보를 설계하고, 구조를 예측해 평가한 뒤, 실험할 후보 목록(FASTA, PDB, CSV)을 내보내는 **연구실 내부용 웹앱**이다.

> **점수는 우선순위 보조 지표이며 실제 열이력(TH) 예측이 아니다.** 양성 대조 검증(예비)은 "불합격"이었고(`docs/dev/validation-report.md`), 후보 선별에는 쓰되 실험으로 확인해야 한다.

## v1 범위

- **포함:** 시드 기반 서열 최적화(모드 A), ESMFold 구조 QC, IBS 지표, 개발성 플래그, 순위표(가중치 슬라이더), 3D 비교, FASTA/PDB/CSV 내보내기
- **제외(v1.x):** IBS 모티프 de novo 설계(모드 B), 간이 MD, 분류기 학습, 실험 결과 업로드와 점수 보정 → [`docs/dev/v1x-backlog.md`](docs/dev/v1x-backlog.md)

## 빠른 시작 (Windows PowerShell, Python 3.11)

```powershell
# 1) 가상환경과 의존성 (한 번만)
py -3.11 -m venv $env:USERPROFILE\afp-venv
$env:USERPROFILE\afp-venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu124
$env:USERPROFILE\afp-venv\Scripts\python.exe -m pip install -r requirements.txt

# 2) 설치 검증 (첫 실행 때 ESM-2 약 2.6GB, ESMFold 약 8.4GB를 Hugging Face에서 내려받는다)
$env:USERPROFILE\afp-venv\Scripts\python.exe -m afp.check

# 3) 앱 실행
$env:USERPROFILE\afp-venv\Scripts\python.exe -m streamlit run app/Home.py
```

이하 명령은 가상환경의 `python`을 쓴다고 가정한다 (`& $env:USERPROFILE\afp-venv\Scripts\python.exe ...`).

## 명령줄

```powershell
python -m afp.check                                   # 설치 검증 (--quick: 모델 로딩 생략)
python -m afp.cli seeds                               # 시드 목록과 검증
python -m afp.cli design --seed type3_hplc12 --n 100 --max-mut 8 --rng-seed 1
python -m afp.cli evaluate --run <run_id>             # 평가 단계만 다시 실행
python -m afp.cli rerun --run <run_id>                # 같은 파라미터로 재실행
python -m afp.cli export --run <run_id> --top 10 --out my_batch
python -m afp.cli validate [--predicted]              # 양성 대조 검증
python scripts/show_run.py <run_id>                   # 결과 요약
```

`--backend mock`은 가짜 모델로 빠르게 동작을 확인하는 용도다(결과는 의미 없음).

## 테스트

```powershell
python -m pytest                 # 단위·통합 (모델 가중치 불필요, 약 1분)
python -m pytest -m gpu          # 실제 ESM-2/ESMFold 사용
python -m pytest -m regression   # 고정 시드 품질 비율 회귀 (느림)
```

## 폴더 구조

```
app/            Streamlit 페이지 (Home, Runs, Ranking)
afp/            파이프라인 패키지 (io, design, evaluate, runner, export, models, pipeline, cli)
data/seeds/     시드 AFP (seed.json + structure.pdb), data/controls/ 음성 대조
scripts/        시드 준비, 기준선 측정, 결과 요약
tests/          unit / integration / gpu / regression
docs/           계획, PRD, 개발·운영 문서
runs/ cache/ exports/   실행 결과·캐시·내보내기 (git 제외). 프로젝트 경로가 길면 ~/afp-data 아래에 만든다
```

## 문서

[`docs/README.md`](docs/README.md)에 읽는 순서가 있다. 사용법은 [`docs/user-guide.md`](docs/user-guide.md), 운영은 [`docs/ops.md`](docs/ops.md), 출시 점검은 [`docs/dev/release-checklist.md`](docs/dev/release-checklist.md)를 본다.
