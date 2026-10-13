# 운영 문서

## 설치 검증

```powershell
python -m afp.check                 # 전체 (모델 포함)
python -m afp.check --quick         # 모델 로딩 생략
python -m afp.check --report docs/dev/env-report.md
```

항목: Python, 패키지, GPU, 시드·대조군 검증, FASTA/PDB 왕복, SASA, ESM-2, ESMFold. 하나라도 실패하면 종료 코드 1이다.

## 환경과 위치

| 항목 | 위치 / 값 |
| --- | --- |
| 가상환경 | `%USERPROFILE%\afp-venv` (프로젝트 밖. 용량이 크고 옮길 수 없다) |
| 모델 가중치 | `%USERPROFILE%\.cache\huggingface` — ESM-2 650M 약 2.6GB, ESMFold 약 8.4GB. `HF_HOME`으로 바꿀 수 있다 |
| 실행 결과·캐시·내보내기 | 프로젝트의 `runs/`, `cache/`, `exports/`. 프로젝트 경로가 150자를 넘으면 `%USERPROFILE%\afp-data` 아래에 만든다. `AFP_DATA_DIR`(또는 `AFP_RUNS_DIR`, `AFP_CACHE_DIR`, `AFP_EXPORTS_DIR`)로 직접 지정할 수 있다 |
| 동시 실행 한도 | 기본 1개. `AFP_MAX_CONCURRENT`로 바꾼다 |

Windows는 경로 길이가 260자를 넘으면 파일을 만들 수 없다. 작업 폴더가 깊은 위치에 있으면 `AFP_DATA_DIR`을 짧은 경로로 지정한다.

## GPU와 실행 시간

- ESM-2(650M)는 fp16으로 약 1.3GB라 작은 GPU에서도 돈다.
- **ESMFold는 VRAM이 약 14GB 이상일 때만 GPU를 쓴다.** 그보다 작으면(예: RTX 3050 6GB) 자동으로 CPU에서 실행한다(약 13GB RAM 사용). 장치를 강제하려면 홈의 고급 설정 또는 `--device cuda|cpu`.
- 이 PC(RTX 3050 6GB, CPU 실행) 측정값: 37잔기 약 4초, 66잔기 약 10초, 82잔기 약 19초. 후보 100개는 약 17~30분이다. 같은 서열은 `cache/structures`에 캐시되어 다시 예측하지 않는다.
- 모델을 처음 불러오는 데 수 초~수십 초가 걸린다. 실행마다 새 프로세스라 매번 로딩된다.

## 문제 해결

| 증상 | 원인과 대처 |
| --- | --- |
| `FileNotFoundError ... 파일 이름이나 확장명이 너무 깁니다` | 경로 260자 초과. `AFP_DATA_DIR`을 짧은 경로로 지정 |
| 구조 예측이 `failed: ... out of memory` | 후보 길이가 길거나 메모리 부족. 다른 프로그램을 닫거나 `--device cpu`. 실패한 후보는 `qc_failed`로 표시되고 나머지는 계속 진행된다 |
| 실행이 "실패"인데 오류 메시지가 없다 | 프로세스가 비정상 종료됐다. 해당 실행 폴더의 `log.txt`를 본다 |
| "동시 실행 한도에 도달했습니다" | 다른 실행이 돌고 있다. 끝나길 기다리거나 취소한다. 죽은 프로세스는 자동으로 "실패"로 정리된다 |
| 모델 다운로드 실패 | 서버의 인터넷/방화벽 확인. 오프라인이면 다른 PC에서 받은 `huggingface` 캐시를 복사하고 `HF_HOME`을 지정 |
| 3D 뷰어가 비어 있다 | 3Dmol 라이브러리를 `cdn.jsdelivr.net`에서 불러온다. 브라우저가 인터넷에 접근할 수 없으면 동작하지 않는다 (오프라인 배포는 라이브러리를 직접 호스팅해야 한다) |
| `Warning: unauthenticated requests to the HF Hub` | 무해한 경고. 필요하면 `HF_TOKEN`을 설정 |
| `contact_head ... MISSING` 로그 | ESMFold 체크포인트에 없는 접촉 예측 헤드가 새로 초기화됐다는 안내. 구조 예측에는 영향이 없다 |

## 정리와 백업

- `runs/`의 폴더는 독립적이다. 오래된 실행은 폴더째 지워도 된다(`cache/structures`의 구조 캐시는 서열 해시로 재사용된다).
- 내보낸 패키지(`exports/`)는 실험 기록으로 남기고, 재현에 필요한 `params.json`, `versions.json`이 들어 있다.
- 시드(`data/seeds`)와 음성 대조(`data/controls`)는 저장소에 포함되며, 시드를 바꾸면 `python -m afp.check`와 `python -m afp.cli validate`를 다시 실행한다.

## 접근과 보안

- 사내 네트워크 또는 VPN 안에서만 노출한다. 외부 서버로 가는 것은 모델 다운로드와 3Dmol 스크립트뿐이며, 서열과 구조는 앱 서버 밖으로 나가지 않는다.
- 다른 PC에서 접속하려면 `python -m streamlit run app/Home.py --server.address 0.0.0.0 --server.port 8501`로 실행하고 방화벽을 사내 범위로 제한한다. 앱에는 로그인이 없다.

## 업데이트 절차

1. 코드를 갱신하고 `pip install -r requirements.txt`를 다시 실행한다.
2. `python -m pytest` (단위·통합)를 실행한다.
3. `python -m afp.check`로 모델과 환경을 확인한다.
4. 설계 로직이나 모델 버전이 바뀌면 `python scripts/regression_baseline.py`로 기준선을 다시 만들고 변경 이유를 기록한다.
