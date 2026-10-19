# AFP Designer FastAPI 마이그레이션 계획

작성일: 2026-10-19  
대상 저장소: `AFP1`  
기준 커밋: `f90e00f` (`Initial commit: AFP Designer v1`)

## 1. 문서 목적

이 문서는 현재 Streamlit 중심의 AFP Designer를 FastAPI 기반 서비스 구조로 점진적으로 전환하는 방안을 정리한다. 목표는 기존 설계·평가 알고리즘을 다시 작성하는 것이 아니라, 이미 잘 분리되어 있는 `afp/` 코어 기능 앞에 안정적인 HTTP API 경계를 추가하는 것이다.

FastAPI는 백엔드 프레임워크이므로 그 자체가 현재 Streamlit 화면을 대체하지는 않는다. 권장 전환 순서는 다음과 같다.

1. 기존 `afp/` 코어와 파일 기반 실행 형식은 유지한다.
2. FastAPI로 시드, 실행, 순위, 내보내기 기능을 제공한다.
3. 기존 Streamlit을 FastAPI의 클라이언트로 전환한다.
4. 필요가 확인되면 이후 React/Next.js 같은 별도 프런트엔드로 교체한다.

이 방식은 한 번에 전체 UI와 백엔드를 바꾸는 것보다 회귀 범위를 작게 유지하며, 기존 CLI와 95개의 기본 테스트 자산도 계속 활용할 수 있다.

## 2. 현재 구조 평가

현재 구조는 FastAPI 전환에 비교적 유리하다.

```text
Streamlit UI
    ├─ app/Home.py
    ├─ app/pages/1_Runs.py
    └─ app/pages/2_Ranking.py
             │
             ▼
Python core
    ├─ afp/io
    ├─ afp/design
    ├─ afp/evaluate
    ├─ afp/runner
    ├─ afp/export
    └─ afp/pipeline.py
             │
             ▼
Filesystem
    ├─ data/seeds
    ├─ runs
    ├─ cache
    └─ exports
```

장점:

- UI와 계산 로직이 이미 상당 부분 분리되어 있다.
- CLI와 Streamlit이 동일한 코어 함수를 사용한다.
- 실행 상태와 결과가 파일로 명확하게 저장된다.
- 실제 모델 없이 API 테스트에 활용할 수 있는 mock backend가 있다.
- 작업 생성, 상태 조회, 취소, 내보내기 함수가 이미 존재한다.

FastAPI 전환 시 보완할 부분:

- API 요청·응답에 사용할 명시적인 Pydantic 스키마가 없다.
- UI와 CLI가 파일 경로와 설정 객체를 직접 다루는 부분이 있다.
- 장시간 작업의 상태 관리는 가능하지만 다중 API worker 환경을 고려한 잠금은 없다.
- `NaN`, `Path`, pandas 타입처럼 JSON으로 바로 반환하기 어려운 값이 후보 데이터에 포함된다.
- 인증, CORS, 업로드 제한, API 오류 형식이 정의되어 있지 않다.
- 내보내기 경로를 서버가 안전하게 통제하도록 보완할 필요가 있다.

## 3. 마이그레이션 목표와 비목표

### 3.1 목표

- 시드 목록·등록, 설계 실행, 상태 조회, 취소, 순위 계산, 내보내기를 HTTP API로 제공한다.
- 기존 CLI와 코어 파이프라인의 동작을 유지한다.
- 장시간 모델 작업은 HTTP 요청과 분리한다.
- 요청과 응답을 타입이 명확한 계약으로 정의한다.
- 기존 실행 폴더를 마이그레이션 없이 그대로 조회할 수 있게 한다.
- 자동 생성되는 OpenAPI 문서를 클라이언트 계약의 기준으로 사용한다.
- 향후 별도 웹 프런트엔드와 작업 큐를 도입할 수 있는 경계를 마련한다.

### 3.2 초기 마이그레이션의 비목표

- AFP 설계 알고리즘이나 점수 체계 변경
- 첫 단계부터 Redis, Celery, PostgreSQL을 도입하는 것
- Streamlit을 즉시 제거하는 것
- de novo 모드 B 또는 MD 기능 구현
- 다중 GPU 스케줄러 구현
- 외부 공개 서비스 수준의 계정·과금 시스템

## 4. 권장 목표 구조

```text
Client
    ├─ Streamlit API client       # 1차 전환
    ├─ Swagger / ReDoc            # 개발·검증
    └─ Web frontend               # 선택적 후속 단계
                 │
                 ▼
FastAPI (`afp/api`)
    ├─ routers                    # HTTP 경계
    ├─ schemas                    # Pydantic 요청·응답
    ├─ dependencies               # 설정, repository, 인증
    └─ error_handlers             # 공통 오류 형식
                 │
                 ▼
Application services (`afp/services`)
    ├─ SeedService
    ├─ RunService
    ├─ RankingService
    └─ ExportService
                 │
                 ▼
Existing core
    ├─ afp/io
    ├─ afp/design
    ├─ afp/evaluate
    ├─ afp/runner
    ├─ afp/export
    └─ afp/pipeline.py
                 │
                 ▼
FilesystemRepository
    ├─ built-in seeds
    ├─ user seeds
    ├─ runs
    ├─ cache
    └─ exports
```

핵심 원칙은 HTTP router가 `config.RUNS_DIR`이나 CSV 파일을 직접 읽지 않게 하는 것이다. router는 요청 검증과 HTTP 상태 코드만 담당하고, 실제 작업은 service와 repository 계층에 위임한다.

CLI도 점진적으로 service 계층을 호출하게 바꾸면 API와 CLI 사이의 동작 차이를 줄일 수 있다.

## 5. 권장 디렉터리 구조

```text
AFP1/
  afp/
    api/
      __init__.py
      main.py
      dependencies.py
      errors.py
      middleware.py
      routers/
        health.py
        seeds.py
        runs.py
        candidates.py
        exports.py
        validation.py
      schemas/
        common.py
        seeds.py
        runs.py
        candidates.py
        exports.py
    services/
      seed_service.py
      run_service.py
      ranking_service.py
      export_service.py
    repositories/
      base.py
      filesystem.py
    ...기존 코어 모듈
  app/
    api_client.py
    Home.py
    pages/
  tests/
    api/
    unit/
    integration/
```

초기에는 `FilesystemRepository` 하나만 구현한다. 실제로 두 번째 저장 방식이 필요해질 때 `SQLiteRepository` 또는 DB 구현을 추가한다.

## 6. 요청 처리와 장시간 작업 원칙

### 6.1 설계 실행을 API 프로세스 안에서 직접 수행하지 않는다

ESM-2와 ESMFold는 메모리와 실행 시간이 큰 작업이다. FastAPI의 `BackgroundTasks`는 응답 이후 같은 애플리케이션 프로세스에서 작은 후처리를 실행할 때 적합하며, 공식 문서도 무거운 계산에는 별도 작업 도구를 고려하도록 안내한다. 따라서 AFP 설계 실행에는 현재의 서브프로세스 실행기인 [`afp/runner/launcher.py`](afp/runner/launcher.py)를 우선 재사용한다. 참고: [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).

권장 흐름:

```text
POST /api/v1/runs
        │
        ├─ 요청 스키마 검증
        ├─ 실행 폴더 생성
        ├─ 전용 서브프로세스 시작
        └─ 202 Accepted + run_id 반환

GET /api/v1/runs/{run_id}
        └─ status.json을 표준 응답으로 변환
```

API 요청은 작업 완료를 기다리지 않는다. 작업 생성에 성공하면 `202 Accepted`, `run_id`, 상태 조회 URL을 반환한다.

### 6.2 초기 운영은 API worker 1개를 권장한다

현재 동시 실행 한도 확인과 프로세스 시작은 하나의 원자적 연산이 아니므로 여러 Uvicorn worker를 사용하면 동시에 작업이 시작될 가능성이 있다. 또한 향후 API 프로세스에 모델을 올리면 worker 수만큼 메모리가 중복될 수 있다.

초기 운영 구성:

- FastAPI/Uvicorn worker: 1개
- GPU 설계 작업: 기존 별도 서브프로세스
- 동시 실행: 기본 1개
- 상태 저장: 기존 파일 기반 형식

다중 사용자 요구가 실제로 생기면 그때 파일 잠금 또는 SQLite 트랜잭션을 먼저 추가하고, 필요 시 Redis 기반 큐나 별도 worker 서비스로 발전시킨다. Uvicorn 다중 worker 운영 방식은 [FastAPI 공식 배포 문서](https://fastapi.tiangolo.com/deployment/server-workers/)를 기준으로 검토한다.

### 6.3 모델은 웹 프로세스보다 작업 프로세스에서 관리한다

FastAPI의 `lifespan`은 시작과 종료 시 공유 리소스를 준비하는 공식 방식이며 ML 모델 로딩에도 사용할 수 있다. 다만 현재 구조에서는 API 프로세스가 모델 추론을 수행하지 않으므로 웹 서버의 lifespan에서 ESM 모델을 로딩하지 않는 편이 낫다. 참고: [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).

향후 전용 GPU worker가 도입되면 worker가 시작될 때 모델을 한 번 로딩하고 여러 작업에서 재사용하도록 개선할 수 있다.

## 7. API 설계안

모든 엔드포인트는 `/api/v1` 아래에 둔다. API 버전은 경로에 포함하고, 파일 포맷의 `schema_version`은 별도로 관리한다.

### 7.1 시스템 상태

| Method | Path | 설명 | 정상 상태 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/health/live` | 프로세스 생존 확인 | 200 |
| `GET` | `/api/v1/health/ready` | 설정·필수 디렉터리·작업 실행 가능 여부 | 200 / 503 |
| `GET` | `/api/v1/meta` | API, AFP, Python 버전과 기능 플래그 | 200 |

`ready`에서 실제 ESM 모델을 매번 로딩하지 않는다. 모델 다운로드와 GPU 상태를 깊게 확인하는 기능은 별도 관리자용 진단 API 또는 기존 `python -m afp.check`로 유지한다.

### 7.2 시드

| Method | Path | 설명 | 정상 상태 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/seeds` | 사용 가능한 시드 목록 | 200 |
| `GET` | `/api/v1/seeds/{seed_id}` | 시드 상세와 IBS 근거 | 200 |
| `GET` | `/api/v1/seeds/{seed_id}/structure` | 시드 PDB 다운로드 | 200 |
| `POST` | `/api/v1/seeds` | PDB 또는 FASTA 기반 시드 등록 | 201 |

파일 업로드는 전체 내용을 메모리에 읽는 `bytes`보다 `UploadFile`을 사용한다. FastAPI에서 multipart 업로드를 받으려면 `python-multipart`가 필요하다. 참고: [FastAPI Request Files](https://fastapi.tiangolo.com/tutorial/request-files/).

시드 등록 요청은 `multipart/form-data`로 정의한다.

- `file`: PDB 또는 FASTA
- `seed_id`
- `name`
- `chain`
- `ibs_residues`
- `residue_offset`
- `afp_type`

서버는 업로드 파일명을 저장 경로로 사용하지 않는다. 파일 내용, 시드 ID, chain을 검증한 뒤 서버가 안전한 저장 위치를 결정한다.

### 7.3 실행

| Method | Path | 설명 | 정상 상태 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/runs` | 실행 목록, 상태·시드 필터 | 200 |
| `POST` | `/api/v1/runs` | 새 설계 실행 생성 | 202 |
| `GET` | `/api/v1/runs/{run_id}` | 실행 상세와 상태 | 200 |
| `POST` | `/api/v1/runs/{run_id}/cancel` | 실행 취소 요청 | 202 / 409 |
| `POST` | `/api/v1/runs/{run_id}/rerun` | 같은 설정으로 새 실행 | 202 |
| `POST` | `/api/v1/runs/{run_id}/evaluation` | 평가 단계 재실행 | 202 |
| `GET` | `/api/v1/runs/{run_id}/log` | 제한된 마지막 로그 조회 | 200 |

실행 생성 요청 예시:

```json
{
  "seed_id": "type3_hplc12",
  "n_candidates": 100,
  "max_mutations": 8,
  "near_ibs_angstrom": 5.0,
  "temperature": 1.0,
  "rng_seed": 1,
  "backend": "real",
  "device": "auto",
  "weights": {
    "structure": 0.3,
    "ibs": 0.0,
    "sequence_plausibility": 0.6,
    "developability": 0.1
  }
}
```

응답 예시:

```json
{
  "run_id": "20261019-143000-type3_hplc12-a1b2c3",
  "state": "queued",
  "status_url": "/api/v1/runs/20261019-143000-type3_hplc12-a1b2c3",
  "created_at": "2026-10-19T14:30:00+09:00"
}
```

`POST /runs`는 선택적으로 `Idempotency-Key`를 받아 네트워크 재시도로 동일 작업이 중복 생성되는 것을 막는 방안을 권장한다.

### 7.4 후보와 순위

| Method | Path | 설명 | 정상 상태 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/runs/{run_id}/candidates` | 후보 목록과 지표 | 200 |
| `GET` | `/api/v1/runs/{run_id}/candidates/{cand_id}` | 후보 상세 | 200 |
| `GET` | `/api/v1/runs/{run_id}/candidates/{cand_id}/structure` | 후보 PDB | 200 |
| `POST` | `/api/v1/runs/{run_id}/ranking` | 가중치·필터 기반 임시 순위 계산 | 200 |

후보 목록은 다음 query를 지원할 수 있다.

- `offset`, `limit`
- `qc_passed`
- `min_plddt`, `max_rmsd`
- `include_flags`, `exclude_flags`
- `sort`, `order`

순위 계산은 원본 `candidates.csv`를 덮어쓰지 않고 요청 가중치에 따른 결과만 반환한다. 사용자가 새 기본 점수로 확정 저장하려면 별도의 버전이 있는 평가 작업으로 처리한다.

응답 변환 규칙:

- `NaN`, `Infinity` → JSON `null`
- `Path` → 노출하지 않거나 API URL로 변환
- NumPy 정수·실수 → Python 기본 타입
- 시간 → timezone이 포함된 ISO 8601 문자열
- 절대 로컬 경로 → 응답에 포함하지 않음

### 7.5 내보내기

| Method | Path | 설명 | 정상 상태 |
| --- | --- | --- | --- |
| `POST` | `/api/v1/runs/{run_id}/exports` | 후보 패키지 생성 | 201 |
| `GET` | `/api/v1/exports/{export_id}` | manifest 조회 | 200 |
| `GET` | `/api/v1/exports/{export_id}/download` | ZIP 다운로드 | 200 |

요청 예시:

```json
{
  "candidate_ids": ["c0001", "c0004", "c0012"],
  "apply_run_qc_thresholds": true,
  "include_seed_control": true
}
```

클라이언트가 서버 경로 또는 내보내기 폴더명을 직접 지정하지 않게 한다. 서버가 `export_id`와 저장 위치를 생성하고, 모든 경로가 `EXPORTS_DIR` 내부인지 확인한다.

### 7.6 진행 상황 전달

1차 구현은 2초 간격의 `GET /runs/{run_id}` polling으로 충분하다. 현재 Streamlit도 같은 방식으로 상태 파일을 확인하므로 동작을 그대로 재사용할 수 있다.

진행 이벤트를 실시간으로 제공할 필요가 확인되면 다음 엔드포인트를 추가한다.

```text
GET /api/v1/runs/{run_id}/events
Content-Type: text/event-stream
```

단방향 진행률·로그 전달에는 WebSocket보다 SSE가 단순하다. FastAPI는 공식 SSE 지원을 제공하지만 비교적 최근에 추가된 기능이므로, 사용할 FastAPI 버전을 lockfile로 고정하고 호환성을 확인한 뒤 도입한다. 참고: [FastAPI Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/).

## 8. Pydantic 스키마 원칙

API 요청 스키마와 내부 파일 형식을 같은 객체로 바로 사용하지 않는다. HTTP 계약과 저장 포맷은 변화 속도가 다르기 때문이다.

권장 주요 모델:

- `RunCreateRequest`
- `RunAcceptedResponse`
- `RunSummaryResponse`
- `RunDetailResponse`
- `RunStatusResponse`
- `SeedSummaryResponse`
- `SeedDetailResponse`
- `CandidateResponse`
- `RankingRequest`
- `RankingResponse`
- `ExportCreateRequest`
- `ExportResponse`
- `ApiErrorResponse`

검증 규칙 예시:

- 후보 수: 1 이상이며 운영 상한 이하
- 최대 변이 수: 1 이상, 시드의 변이 가능 위치 수 이하
- 온도: 0보다 큰 유한한 값
- 가중치: 모두 0 이상이며 합이 0보다 큼
- `seed_id`, `run_id`, `cand_id`: 경로 구분자 없는 제한된 문자 집합
- IBS 잔기: 중복 없음, 구조 범위 안, 최소 개수 충족
- 업로드 크기와 서열 길이: 서버 설정 상한 이하

내부 `InputError`는 API 오류 응답으로 일관되게 변환한다.

```json
{
  "error": {
    "code": "invalid_seed",
    "message": "구조에 없는 IBS 잔기 번호가 있습니다.",
    "details": {"residues": [103]},
    "request_id": "req_01J..."
  }
}
```

권장 HTTP 상태:

| 상태 | 사용 예 |
| --- | --- |
| 400 | 요청 형식은 맞지만 조합이 유효하지 않음 |
| 404 | 시드, 실행, 후보, 내보내기를 찾지 못함 |
| 409 | 이미 실행 중, 취소 불가 상태, 중복 시드 ID |
| 413 | 업로드 크기 초과 |
| 422 | 필드 검증 실패 |
| 429 | 작업 생성 빈도 또는 동시 실행 한도 초과 |
| 503 | 실행 환경 또는 GPU worker 준비 안 됨 |

## 9. 서비스와 저장소 계층

### 9.1 Service 책임

`RunService` 예시:

- `create_run(request) -> RunAccepted`
- `list_runs(filters) -> list[RunSummary]`
- `get_run(run_id) -> RunDetail`
- `cancel_run(run_id) -> RunStatus`
- `rerun(run_id) -> RunAccepted`
- `evaluate(run_id) -> RunAccepted`

Service는 HTTP 상태 코드를 알지 않는다. 대신 `RunNotFound`, `InvalidRunState`, `CapacityExceeded` 같은 애플리케이션 예외를 발생시키고 API 계층이 HTTP 응답으로 변환한다.

### 9.2 Repository 책임

`FilesystemRepository`는 다음 세부사항을 한곳에 모은다.

- 실행 ID를 안전한 경로로 변환
- `params.json`, `status.json`, `candidates.csv` 읽기
- JSON/CSV 타입 정규화
- 실행 목록 정렬과 필터
- 경로가 지정된 루트 밖으로 나가지 않는지 확인
- 원자적 파일 쓰기
- 기존 실행의 스키마 버전 호환

이 계층을 두면 API router, Streamlit, CLI가 파일 레이아웃을 직접 해석하지 않게 할 수 있다.

## 10. 기존 데이터 마이그레이션

초기 FastAPI 도입에는 DB 마이그레이션이 필요하지 않다. 기존 실행 폴더를 그대로 유지하고 repository가 읽도록 한다.

권장 순서:

1. 현재 파일을 변경하지 않고 읽는 `FilesystemRepository`를 만든다.
2. 새 실행부터 `schema_version`을 `params.json`, `status.json`, `scoring.json`, `manifest.json`에 기록한다.
3. 구버전 파일에는 버전이 없으면 `version=1`로 해석한다.
4. 새 필드는 기본값을 적용하되 원본 실행 파일을 자동으로 덮어쓰지 않는다.
5. 필요하면 별도 `migrate-run` 명령으로 복사본을 만든 뒤 변환한다.

시드 저장 위치는 다음처럼 분리하는 방안을 권장한다.

```text
data/seeds/                 # 저장소에 포함된 검증 시드, 읽기 전용
${AFP_DATA_DIR}/user-seeds  # API로 등록한 사용자 시드
```

API 업로드가 Git 저장소 내부의 `data/seeds`를 직접 변경하지 않게 하면 배포 이미지와 사용자 데이터를 명확히 분리할 수 있다.

SQLite는 다음 조건 중 하나가 생길 때 도입한다.

- 실행 수가 많아 디렉터리 전체 스캔이 느려짐
- 여러 사용자의 소유권과 검색 조건이 필요함
- 여러 API 프로세스에서 원자적 동시 실행 제어가 필요함
- 작업 상태와 감사 로그를 트랜잭션으로 관리해야 함

구조 PDB, FASTA, ZIP 같은 큰 파일은 SQLite 도입 후에도 파일시스템 또는 객체 저장소에 두는 편이 적절하다.

## 11. Streamlit 전환 전략

### 단계 A — 기존 직접 호출 유지

FastAPI를 추가하되 Streamlit은 기존 Python 함수를 계속 호출한다. 이 단계에서 API 계약과 테스트를 먼저 안정화한다.

### 단계 B — 공통 API client 추가

`app/api_client.py`에 다음 메서드를 둔다.

- `list_seeds()`
- `create_seed()`
- `create_run()`
- `get_run()`
- `list_candidates()`
- `rank_candidates()`
- `create_export()`
- `download_export()`

`AFP_API_BASE_URL`이 설정되면 HTTP를 사용하고, 개발 중에는 기존 직접 호출 모드를 선택적으로 유지할 수 있다.

### 단계 C — 페이지별 전환

1. Runs 페이지의 조회 기능
2. Ranking 페이지의 후보·순위 조회
3. Home의 실행 생성·취소
4. 시드 업로드
5. 내보내기와 ZIP 다운로드

읽기 기능부터 옮기면 장애 시 되돌리기 쉽다. 각 페이지 전환 후 기존 통합 테스트와 API 계약 테스트를 함께 실행한다.

### 단계 D — 직접 호출 제거

모든 페이지가 API를 사용하고 한 릴리스 이상 안정적으로 운영된 뒤 Streamlit의 코어 직접 import를 제거한다. 이후 Streamlit 유지 또는 별도 웹 프런트엔드 전환을 결정한다.

## 12. 인증, 권한, 보안

### 12.1 배포 범위별 권장안

| 환경 | 권장 보호 방식 |
| --- | --- |
| 개인 PC의 `127.0.0.1` | 인증 생략 가능, 외부 바인딩 금지 |
| 연구실 내부망 | reverse proxy 인증 또는 API key, 방화벽 allowlist |
| 별도 웹 프런트엔드 | 사용자 인증, 세션 또는 bearer token, 명시적 CORS |
| 외부 공개 | 사용자별 권한, 속도 제한, 업로드 격리, 감사 로그 필수 |

### 12.2 기본 보안 요구사항

- `run_id`, `seed_id`, `export_id`를 경로 문자열로 직접 결합하지 않는다.
- `Path.resolve()` 후 허용 루트의 하위인지 확인한다.
- 업로드 파일명은 표시용으로만 사용한다.
- reverse proxy와 애플리케이션 양쪽에서 업로드 크기를 제한한다.
- 내보내기 API는 임의 서버 경로를 입력받지 않는다.
- 로그 응답은 최대 줄 수와 크기를 제한하고 토큰·환경변수를 가린다.
- 예외 traceback과 절대 로컬 경로를 클라이언트에 노출하지 않는다.
- CORS는 실제 UI origin만 허용한다. 별도 origin을 쓰는 경우 [FastAPI CORS 문서](https://fastapi.tiangolo.com/tutorial/cors/)에 따라 명시적으로 설정한다.
- 상태 변경 요청에는 인증과 권한 확인을 적용한다.

## 13. 설정 관리

환경 변수는 `pydantic-settings` 기반 `Settings` 객체 한곳에서 읽도록 한다.

권장 설정:

```text
AFP_ENV=development|test|production
AFP_DATA_DIR=...
AFP_RUNS_DIR=...
AFP_CACHE_DIR=...
AFP_EXPORTS_DIR=...
AFP_USER_SEEDS_DIR=...
AFP_MAX_CONCURRENT=1
AFP_MAX_UPLOAD_MB=20
AFP_API_KEY=...
AFP_CORS_ORIGINS=...
AFP_LOG_LEVEL=INFO
```

설정 객체는 요청마다 새로 만들지 않고 캐시된 dependency로 주입한다. 설정 패턴은 [FastAPI Settings 공식 가이드](https://fastapi.tiangolo.com/advanced/settings/)를 참고한다.

비밀값은 저장소와 `versions.json`에 기록하지 않는다. 실행 provenance에는 비밀값을 제외한 설정만 저장한다.

## 14. 테스트 전략

FastAPI 전환 후에도 기존 코어 테스트 95개는 유지한다. 새 테스트는 API 계약과 경계 조건에 집중한다.

### 14.1 단위 테스트

- Pydantic 필드 범위와 교차 검증
- JSON 직렬화: NaN→null, NumPy→기본 타입
- 애플리케이션 예외→HTTP 오류 변환
- ID와 경로 검증
- repository의 구버전 스키마 읽기

### 14.2 API 테스트

FastAPI 공식 문서의 `TestClient` 방식으로 HTTP 계층을 테스트한다. 참고: [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/).

- health/live, health/ready
- 시드 목록·상세·업로드
- mock backend 실행 생성→완료 polling
- 잘못된 상태에서 취소 시 409
- 후보 pagination·필터·순위 재계산
- PDB와 ZIP 다운로드
- 공통 오류 응답 구조
- 인증 성공·실패
- OpenAPI schema snapshot

### 14.3 보안 회귀 테스트

- `../`, 절대 경로, URL encoded path traversal
- symlink를 통한 루트 이탈
- 허용되지 않은 확장자와 oversized upload
- 다중 FASTA와 모호한 PDB chain
- 임의 `structure_path`가 포함된 변조 CSV
- export overwrite 시 외부 폴더 보존
- 로그와 오류 응답에 절대 경로·비밀값이 없는지 확인

### 14.4 실제 모델 테스트

기존 `gpu`, `regression` 마커는 API 테스트와 분리한다. API의 실제 모델 smoke test는 후보 1~3개로 제한하고, 정기 GPU 환경에서만 실행한다.

## 15. 관찰 가능성

모든 요청과 실행을 연결할 수 있도록 다음 필드를 구조화 로그에 포함한다.

- `request_id`
- `run_id`
- `seed_id`
- `route`
- `method`
- `status_code`
- `duration_ms`
- `state`, `stage`, `progress`
- 오류 code와 예외 종류

로그에는 전체 서열, 업로드 원문, API key를 기본적으로 기록하지 않는다.

권장 운영 지표:

- API 요청 수, 오류율, p50/p95 응답 시간
- queued/running 작업 수
- 작업 성공·취소·오류 비율
- 후보당 구조 예측 시간
- GPU/CPU 메모리와 디스크 사용량
- 캐시 적중률

## 16. 배포안

### 16.1 개발 환경

```bash
uvicorn afp.api.main:app --host 127.0.0.1 --port 8000 --reload
```

`--reload`는 개발 환경에서만 사용한다. 자동 reload로 API 프로세스가 재시작되어도 별도 실행 프로세스와 상태 파일이 일관되게 처리되는지 테스트한다.

### 16.2 연구실 단일 서버

```text
Browser / Streamlit
        │ HTTPS
        ▼
Reverse proxy
        │ localhost
        ▼
FastAPI/Uvicorn (1 worker)
        │ subprocess
        ▼
AFP job process (GPU 또는 CPU)
        │
        ▼
Shared data root
```

권장 사항:

- API는 내부 주소에 바인딩하고 reverse proxy만 외부에 노출한다.
- TLS와 인증은 reverse proxy 또는 조직 표준 인증 계층에서 처리한다.
- 데이터 루트와 모델 캐시는 영속 볼륨으로 둔다.
- 애플리케이션 재배포가 실행 결과와 사용자 시드를 지우지 않게 한다.
- GPU 한도 때문에 초기에는 API replica를 늘리기보다 작업 실행 제어를 먼저 안정화한다.

### 16.3 향후 분리형 구성

```text
FastAPI API
    │
    ├─ PostgreSQL/SQLite metadata
    ├─ Redis queue
    └─ Object/file storage
              │
              ▼
        Dedicated GPU worker
```

이 구조는 다중 사용자, 재시도, 예약 실행, 여러 GPU가 필요할 때 검토한다. 초기 마이그레이션에는 포함하지 않는다.

## 17. 단계별 실행 계획

### M0 — 계약과 경계 정리

예상: 1~2일

- `RunParams`, 가중치, ID 검증 스키마 정의
- `InputError`를 애플리케이션 예외 계층으로 정리
- JSON 직렬화 규칙 정의
- 안전한 경로 resolver 구현
- API endpoint와 OpenAPI 계약 확정

완료 조건:

- 기존 CLI 테스트가 그대로 통과한다.
- 잘못된 파라미터를 UI, CLI, API가 같은 규칙으로 처리한다.

### M1 — FastAPI 골격과 읽기 API

예상: 1~2일

- `afp/api/main.py`, router, 공통 오류 응답
- health, meta, seeds, runs 조회
- candidates 조회와 PDB 다운로드
- `FilesystemRepository`
- TestClient 기반 API 테스트

완료 조건:

- 기존 실행 폴더를 변경하지 않고 API에서 조회한다.
- OpenAPI 문서에 모든 response model이 표시된다.

### M2 — 실행 생성과 제어

예상: 2~4일

- 실행 생성 `202 Accepted`
- 상태 조회와 polling
- 취소, 재실행, 평가 재실행
- 동시 실행 한도와 상태 충돌 처리
- idempotency와 request ID

완료 조건:

- mock backend 실행이 HTTP 요청부터 완료 상태까지 이어진다.
- API 프로세스를 재시작해도 기존 작업과 결과를 다시 조회할 수 있다.

### M3 — 순위와 내보내기

예상: 2~3일

- 동적 ranking API
- 공통 QC eligibility 적용
- 서버 생성 `export_id`
- 안전한 ZIP 다운로드
- manifest에 필터·점수 버전 기록

완료 조건:

- UI와 CLI/API가 같은 후보 집합을 내보낸다.
- 경로 탈출 테스트와 외부 디렉터리 보존 테스트가 통과한다.

### M4 — Streamlit API client 전환

예상: 2~4일

- 읽기 페이지부터 API client 적용
- 실행·취소·업로드·내보내기 전환
- 연결 실패, timeout, 재시도 UX
- 직접 호출 fallback을 한 릴리스 동안 유지

완료 조건:

- Streamlit이 `afp` 내부 파일 경로를 직접 읽지 않는다.
- 기존 사용자 시나리오와 AppTest가 통과한다.

### M5 — 운영 보강

예상: 2~4일

- 인증 또는 내부 proxy 연동
- CORS, 업로드 제한, 로그 마스킹
- lockfile과 CI
- 배포 문서와 rollback 절차
- 실제 모델 smoke test

전체 예상은 한 명 기준 약 2~3주이며, 별도 프런트엔드 개발과 과학적 점수 개선은 포함하지 않는다.

## 18. 전환 완료 기준

- 기존 CLI와 기본 테스트 95개가 계속 통과한다.
- API 단위·통합·보안 테스트가 추가된다.
- mock backend의 시드 등록→실행→상태→순위→내보내기 흐름이 HTTP로 완주된다.
- 기존 실행 폴더를 별도 변환 없이 조회할 수 있다.
- API 요청이 장시간 모델 작업을 직접 수행하지 않는다.
- API 재시작 후에도 실행 상태와 결과를 복구한다.
- 서버의 절대 경로가 응답에 노출되지 않는다.
- 내보내기와 업로드가 지정 데이터 루트 밖을 변경하지 않는다.
- Streamlit과 CLI/API의 QC·순위·내보내기 결과가 일치한다.
- OpenAPI 문서와 실제 응답이 계약 테스트로 일치한다.

## 19. 롤백 전략

점진적 전환 중에는 기존 Streamlit 직접 호출 경로를 유지한다.

1. FastAPI 기능은 `AFP_API_BASE_URL`이 있을 때만 사용한다.
2. 파일 형식은 기존 버전과 역호환되게 읽는다.
3. 새 API는 기존 실행 파일을 자동 변환하거나 덮어쓰지 않는다.
4. 페이지별로 API 사용을 feature flag로 켤 수 있게 한다.
5. 문제가 생기면 API flag를 끄고 기존 직접 호출 방식으로 돌아간다.

한 릴리스 이상 API 경로가 안정적으로 운영된 뒤 직접 호출 fallback 제거를 검토한다.

## 20. 착수 전 결정할 항목

| 항목 | 권장 기본값 | 결정이 필요한 이유 |
| --- | --- | --- |
| 전환 범위 | FastAPI backend + 기존 Streamlit 유지 | UI 재작성 없이 위험을 줄일 수 있음 |
| 초기 저장소 | 기존 파일시스템 | 데이터 마이그레이션을 피할 수 있음 |
| 작업 실행 | 기존 서브프로세스 runner | 무거운 작업을 API 요청에서 분리 가능 |
| API worker | 1개 | 동시 실행 경쟁과 GPU 자원 충돌 최소화 |
| 진행률 | polling | 현재 status.json 구조를 그대로 활용 |
| 인증 | localhost 또는 내부 proxy 인증 | 공개 범위에 따라 구현 규모가 달라짐 |
| 사용자 시드 | 데이터 루트의 별도 디렉터리 | Git 저장소와 사용자 데이터 분리 |
| 프런트엔드 | Streamlit API client 우선 | 별도 웹 UI는 사용성 요구 확인 후 결정 |

## 21. 최종 권고

AFP Designer는 계산 로직과 UI가 이미 어느 정도 분리되어 있어 FastAPI 전환을 위해 코어를 다시 작성할 필요가 없다. 가장 안정적인 접근은 기존 코어와 파일 기반 실행 형식을 유지하면서 service, repository, API 계층을 순서대로 추가하는 것이다.

우선순위는 다음과 같이 제안한다.

1. 공통 파라미터·응답 스키마와 안전한 경로 처리를 먼저 만든다.
2. 조회 API로 기존 실행 데이터의 호환성을 확인한다.
3. 현재 서브프로세스 runner를 감싼 비동기 작업 API를 추가한다.
4. 순위와 내보내기의 QC 규칙을 공통화한다.
5. Streamlit을 페이지별로 API client 방식으로 전환한다.
6. 사용량이 늘어날 때 DB와 외부 작업 큐를 도입한다.

즉, 이번 마이그레이션은 “Streamlit을 FastAPI로 교체”하는 작업보다 **현재의 연구 파이프라인을 안정적인 API로 제공하고 UI와 실행 환경을 느슨하게 분리하는 작업**으로 정의하는 것이 적절하다.
