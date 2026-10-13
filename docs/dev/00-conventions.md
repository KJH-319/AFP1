# 개발 공통 규약

M0~M3 개발 문서가 공통으로 참조하는 구조, 데이터 형식, 규칙을 정리한다. 요구사항 ID(F-n)는 [PRD](../02-PRD.md)의 4장을 따른다.

## 1. 원칙

1. **작게 만든다.** v1은 모드 A만 구현한다. PRD의 P2 항목(F-4, F-6, F-14, F-16)은 만들지 않는다.
2. **인프라를 늘리지 않는다.** 큐 서버, DB 서버, 추상 어댑터 계층은 만들지 않는다. 필요해지는 시점에 도입한다.
3. **CLI가 먼저, UI는 얇게.** 모든 기능은 CLI로 먼저 동작시키고 Streamlit은 같은 함수를 호출하는 얇은 껍데기로 둔다.
4. **재현성은 처음부터.** 모든 실행은 난수 시드, 도구 버전, 파라미터를 작업 폴더에 남긴다(F-17).
5. **점수는 보조 지표다.** 점수가 보이는 모든 화면과 내보내기 파일에 "우선순위 보조 지표이며 실제 TH 예측이 아니다"를 넣는다.

## 2. 저장소 구조

```
afp-designer/
  app/                 # Streamlit 페이지 (얇게)
    Home.py            # 설계 실행
    pages/
      1_Runs.py        # 실행 이력 (F-1)
      2_Ranking.py     # 순위표 + 3D (F-11, F-12)
  afp/
    cli.py             # python -m afp.cli ...
    check.py           # 도구 설치 검증 (smoke test)
    config.py          # 경로, 기본 파라미터, 임계값
    io/                # fasta.py, pdb.py, seeds.py (F-2, F-3)
    runner/            # 서브프로세스 실행, status.json (F-13)
    design/mode_a.py   # 서열 최적화 (F-5)
    evaluate/          # structure_qc.py, ibs_metrics.py, afp_similarity.py,
                       # developability.py, scoring.py (F-7~F-11)
    export/            # fasta/pdb/csv 내보내기 (F-15)
    tools.py           # 외부 도구 호출은 이 한 모듈에 모은다
  data/
    seeds/<seed_id>/   # seed.json, structure.pdb
    controls/          # 양성·음성 대조
  runs/                # 실행 결과 (git 제외)
  cache/               # 구조 예측 캐시 (git 제외)
  tests/               # unit/, integration/, regression/
  docs/
  environment.yml
```

## 3. 작업 폴더 형식

실행 한 번이 `runs/<run_id>/` 폴더 하나다. `run_id`는 `YYYYMMDD-HHMMSS-<seed_id>-<짧은해시>` 형식으로 만든다.

```
runs/<run_id>/
  params.json        # 입력 파라미터 (재실행에 사용)
  versions.json      # 도구·모델 버전, git 커밋, 하드웨어
  status.json        # 진행 상태 (UI가 폴링)
  log.txt            # 서브프로세스 로그
  candidates.csv     # 후보별 지표와 점수
  sequences.fasta
  structures/<cand_id>.pdb
```

### status.json

```json
{
  "state": "running",
  "stage": "structure_qc",
  "progress": 0.42,
  "pid": 12345,
  "started_at": "2026-10-12T10:00:00+09:00",
  "updated_at": "2026-10-12T10:07:31+09:00",
  "error": null
}
```

- `state`: `queued` · `running` · `done` · `failed` · `cancelled`
- `stage`: `design` · `structure_qc` · `ibs_metrics` · `scoring` · `export`
- 쓰기는 임시 파일에 쓴 뒤 rename하는 방식으로 원자적으로 한다. UI가 반쯤 쓰인 파일을 읽지 않게 하기 위해서다.
- 취소는 `pid`의 프로세스 트리를 종료하고 `state`를 `cancelled`로 바꾼다.

### params.json (모드 A)

```json
{
  "seed_id": "type3_hplc12",
  "n_candidates": 100,
  "max_mutations": 8,
  "near_ibs_angstrom": 5.0,
  "temperature": 1.0,
  "rng_seed": 1,
  "esm_model": "facebook/esm2_t33_650M_UR50D",
  "structure_model": "facebook/esmfold_v1"
}
```

### candidates.csv 열

| 열 | 설명 | 채우는 단계 |
| --- | --- | --- |
| `cand_id` | `c0001` 형식 | M1 |
| `sequence` | 전체 서열 | M1 |
| `n_mut`, `mutations` | 변이 수, `A12T;K30R` 형식 | M1 |
| `plddt_mean`, `plddt_ibs` | 전체·IBS 영역 평균 pLDDT (0~100) | M1 |
| `rmsd_seed` | 시드 대비 Cα RMSD (Å) | M1 |
| `ibs_planarity`, `ibs_area`, `ibs_lattice_dev`, `ibs_hydrophobic_frac` | IBS 지표 | M2 |
| `esm_llr`, `seq_identity` | AFP 유사도 | M2 |
| `net_charge`, `pI`, `flags` | 개발성 | M2 |
| `score`, `rank` | 종합 점수와 순위 | M2 |
| `structure_path` | 예측 구조 파일 경로 | M1 |

## 4. 시드 형식

`data/seeds/<seed_id>/seed.json`

```json
{
  "id": "type3_hplc12",
  "name": "Type III AFP (HPLC-12)",
  "afp_type": "type3",
  "pdb_id": "(구현 시 확인)",
  "uniprot": "(구현 시 확인)",
  "sequence": "...",
  "ibs_residues": [9, 10, 13, 14],
  "ibs_evidence": ["문헌 DOI 또는 PDB 주석"],
  "numbering": "pdb_author",
  "notes": ""
}
```

- `ibs_residues`는 `numbering` 기준 번호다. 서열 인덱스와 PDB 번호가 다르면 변환 함수를 한 곳(`io/seeds.py`)에서만 쓴다.
- 위 예시의 PDB ID와 잔기 번호는 형식 예시일 뿐이며, 실제 값은 M0에서 문헌과 구조로 검증해 채운다.

## 5. CLI

```
python -m afp.check                                  # 도구 설치 검증
python -m afp.cli design --seed <id> --n 100 --max-mut 8 --rng-seed 1
python -m afp.cli evaluate --run <run_id>            # 평가 단계만 재실행
python -m afp.cli export --run <run_id> --top 10 --out exports/<name>
python -m afp.cli rerun --run <run_id>               # params.json으로 재실행
```

## 6. 테스트 전략

| 마커 | 내용 | 실행 환경 |
| --- | --- | --- |
| `unit` | 파서, 변환, 지표 계산, 점수 정규화. GPU 불필요 | 항상 |
| `integration` | 작은 시드로 N=5 end-to-end. ESM 호출은 가짜 모델로 대체 가능 | 항상 |
| `gpu` | 실제 ESM-2, ESMFold 호출 | GPU 서버 |
| `regression` | 고정 시드 설계 결과와 양성 대조의 기준선 비교 | GPU 서버, M3에서 확정 |

핵심 불변식은 property 테스트로 둔다.

- 어떤 후보에서도 IBS 고정 잔기는 시드와 같다.
- 후보 서열 길이는 시드와 같다(v1은 치환만 지원, 삽입·결실 없음).
- 같은 `params.json`과 `rng_seed`로 재실행하면 `sequences.fasta`가 동일하다.

## 7. 환경 메모

- 개발 PC가 Windows이면 GPU 서버를 Linux로 둘지, WSL2를 쓸지 M0에서 정한다. 외부 도구(MMseqs2 등)의 Windows 지원 여부를 먼저 확인한다.
- 모델 가중치는 첫 실행 때 다운로드된다. 서버가 인터넷에 제한적이면 M0에서 미리 받아 `HF_HOME`을 고정한다.
- 의존성은 `environment.yml`로 고정하고 CUDA, PyTorch 버전을 `versions.json`에 기록한다.

## 8. 완료 정의 (모든 마일스톤 공통)

- 해당 마일스톤의 수용 기준을 자동 테스트 또는 명시된 수동 절차로 통과한다.
- `python -m afp.check`가 통과한다.
- 새로 생긴 설정값과 임계값은 `afp/config.py`에 모여 있고 이 문서 또는 마일스톤 문서에 근거가 적혀 있다.
- 알려진 한계와 미해결 이슈를 마일스톤 문서의 "열린 문제"에 기록한다.
