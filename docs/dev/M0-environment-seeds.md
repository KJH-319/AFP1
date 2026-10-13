# M0. 환경 구축과 시드 큐레이션 (1주)

**목표:** 도구가 돌아가는 환경을 확정하고, 이후 모든 검증의 기준이 될 시드와 대조군을 준비한다. M0가 끝나면 PRD의 오픈 이슈 중 GPU 환경이 닫혀 있어야 한다.

- 관련 요구사항: F-2 (시드 라이브러리), F-17 (재현성 기록의 기반)
- 선행 조건: 없음
- 공통 규약: [00-conventions.md](00-conventions.md)

## 작업 항목

| ID | 작업 | 산출물 |
| --- | --- | --- |
| M0-1 | GPU와 OS 확인. `nvidia-smi`, `torch.cuda.is_available()`, VRAM 용량을 기록하고 실행 OS를 정한다(Windows 네이티브, WSL2, Linux 서버 중 하나) | `docs/dev/env-report.md` |
| M0-2 | conda 환경 구성. Python, PyTorch(CUDA), transformers, biopython, freesasa, pandas, numpy, streamlit, stmol 또는 py3Dmol, pytest | `environment.yml` |
| M0-3 | ESM-2 smoke test. 짧은 서열 하나에서 마스킹된 위치의 아미노산 확률을 계산한다. VRAM이 부족하면 작은 모델(예: 35M)로 대체해 기록한다 | `afp/check.py`의 ESM-2 항목 |
| M0-4 | ESMFold smoke test. 짧은 서열을 예측해 PDB로 저장하고 pLDDT 단위(0~1 또는 0~100)를 확인한다. 긴 서열에서 메모리가 부족하면 chunk size 설정으로 낮출 수 있는지 확인한다 | `afp/check.py`의 ESMFold 항목, VRAM 사용량 기록 |
| M0-5 | 시드 3~5개 선정과 큐레이션. 아래 기준을 따른다 | `data/seeds/*/` |
| M0-6 | 음성 대조 선정. 길이가 시드와 비슷한 비-AFP 구조 소수(시드마다 1~2개)를 고른다 | `data/controls/` |
| M0-7 | 저장소 골격과 `python -m afp.check`. 각 smoke test를 한 명령으로 실행하고 결과를 요약한다 | 리포 스캐폴드 |
| M0-8 | 기준선 측정. 시드의 실험 구조를 ESMFold로 예측해 pLDDT와 Cα RMSD를 구한다. 이 값이 이후 pLDDT·RMSD 임계값의 근거가 된다 | `docs/dev/baseline.md` |

## 시드 선정 기준 (M0-5)

- AFP 유형을 겹치지 않게 고른다. 후보는 Type III(예: HPLC-12), 곤충 TmAFP(β-helix), Type I(α-helix)이며, 하나 더 넣는다면 박테리아 또는 식물 AFP를 고려한다.
- 실험 구조가 PDB에 있는 것을 우선한다. 문서나 이전 계획에 적힌 PDB ID는 후보일 뿐이므로 **PDB와 UniProt에서 직접 확인**한 뒤 `seed.json`에 적는다.
- IBS 잔기는 문헌과 구조에서 근거를 확인해 `ibs_evidence`에 남긴다. 근거를 찾지 못한 시드는 v1에서 제외한다.
- 곤충 β-helix처럼 반복 구조는 ESMFold가 잘 다루지 못할 수 있다. M0-8 기준선에서 pLDDT가 낮으면 그 사실을 기록하고, 해당 시드의 임계값을 따로 둘지 M1 시작 전에 정한다.

## 수용 기준

- [ ] `python -m afp.check`가 ESM-2, ESMFold, freesasa, 파일 입출력 항목을 모두 통과한다.
- [ ] GPU 환경(모델, VRAM, OS)이 문서에 기록되고 PRD 오픈 이슈 1번이 닫힌다.
- [ ] 시드 3~5개가 IBS 잔기 근거와 함께 `seed.json` 검증(스키마, 서열과 구조의 잔기 번호 일치)을 통과한다.
- [ ] 시드마다 기준선(pLDDT, RMSD)이 기록되어 있다.

## 위험과 결정 사항

| 항목 | 내용 |
| --- | --- |
| ESMFold 설치가 까다로움 | transformers 구현을 먼저 시도하고, 안 되면 대안 구현을 쓴다. 어느 쪽이든 `versions.json`에 기록 |
| VRAM 부족 | 긴 서열은 chunk size 조정, 그래도 부족하면 ColabFold를 대안으로 검토(M1 전에 결정) |
| IBS 근거 부족 | 해당 시드 제외. 시드 3개 미만이면 PRD 범위를 재검토 |
| 오프라인 환경 | 모델 가중치를 미리 받아 두고 캐시 경로를 고정 |

## 열린 문제 (작성 후 채운다)

- 선택한 실행 OS와 이유:
- 최종 시드 목록과 제외한 후보:
- 곤충 β-helix의 기준선 pLDDT와 임계값 정책:


## 구현 기록 (2026-10-12)

**환경 (M0-1, M0-2)**

- OS: Windows 11 네이티브(WSL 미설치). 개발·실행 OS를 Windows로 결정했다.
- GPU: RTX 3050 6GB. ESM-2 650M은 GPU(fp16)에서, ESMFold는 VRAM이 14GB에 못 미쳐 CPU에서 실행한다. 상세는 [env-report.md](env-report.md).
- Python 3.11.9, 가상환경 `%USERPROFILE%\afp-venv`(프로젝트 밖), torch 2.6.0+cu124, transformers 5.19.0, biopython 1.88, streamlit 1.65.0. 의존성은 `requirements.txt`(conda 대신 venv).
- 계획과 달라진 점: `freesasa` 대신 Biopython의 Shrake-Rupley(`Bio.PDB.SASA`)를 쓴다(설치 의존성 감소). 3D 뷰어는 `stmol`이 구버전 ipywidgets를 끌어와 충돌해 `py3Dmol`을 직접 쓴다. MMseqs2는 v1에서 쓰지 않는다(치환만 지원해 해밍 거리로 중복을 제거).
- 모델: `facebook/esm2_t33_650M_UR50D`(2.6GB), `facebook/esmfold_v1`(8.4GB).

**smoke test (M0-3, M0-4, M0-7)**: `python -m afp.check` 8/8 통과. ESM-2 masked marginal 3위치 0.33초(GPU), ESMFold 37잔기 7.7초(CPU, 첫 호출). pLDDT는 0~100 범위로 정규화해 쓴다.

**시드와 대조군 (M0-5, M0-6)** — 근거를 확인한 만큼만 기록했다.

| 시드 | PDB | IBS 잔기(문헌 번호) | 근거 수준 | 근거 |
| --- | --- | --- | --- | --- |
| type3_hplc12 | 1HG7 (번호 = 문헌 + 1000) | 9, 14, 15, 18, 44 | literature | Sönnichsen et al. 1996 (RCSB 1KDE 초록): 추정 얼음 결합 잔기 Gln9, Asn14, Thr15, Thr18, Gln44. 구조 서열에서 잔기 종류 일치 확인 |
| tmafp_beetle | 1EZG (번호 = 문헌 + 1) | 16, 26, 28, 38, 40, 50, 52, 62, 64 | literature_partial | PMC5991737 Table 1의 IBS Thr 변이 대상 9개. 이 논문은 IBS Thr가 11개라고 하나 전체 목록이 본문에 없어 2개는 제외 |
| type1_hplc6 | 1WFA | 2, 13, 24, 35 | derived | Sicheri & Yang 1995(반복 모티프 4개). 번호는 11잔기 주기 Thr에서 유도했고 열어본 출처에서 직접 확인하지 못함 |

- 음성 대조: ubiquitin(1UBQ), BPTI(5PTI), GCN4 leucine zipper(2ZTA).
- `type1_hplc6`은 근거 수준이 `derived`라 앱이 경고를 띄운다. 전문가 확인 후 `literature`로 올리거나 제외한다.
- 시드 데이터는 `scripts/prepare_seeds.py`가 `data/_raw`의 RCSB 원본에서 만든다. 스크립트가 문헌이 말한 잔기 종류와 구조 서열이 맞는지 검증한다.

**기준선 (M0-8)**: 세 시드 모두 시드 서열의 ESMFold 예측이 pLDDT 93.6~97.2, 실험 구조 대비 RMSD 0.72~0.79 Å로 임계값(80, 2 Å)을 여유 있게 통과한다. 반복 구조인 곤충 β-helix도 문제없이 예측되어 시드별 임계값은 두지 않았다. 표는 [baseline.md](baseline.md).

## 열린 문제 (답)

- 선택한 실행 OS와 이유: Windows 네이티브. 개발 PC가 Windows이고 의존성이 모두 Windows 휠로 설치되었다. GPU VRAM 때문에 ESMFold는 CPU로 돈다.
- 최종 시드 목록과 제외한 후보: type3_hplc12, tmafp_beetle, type1_hplc6. 제외한 시드는 없다(박테리아·식물 AFP는 v1.x 확장).
- 곤충 β-helix의 기준선 pLDDT와 임계값 정책: pLDDT 93.6, RMSD 0.76 Å. 시드별 임계값 불필요.
