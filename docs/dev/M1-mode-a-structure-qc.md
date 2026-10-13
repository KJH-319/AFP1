# M1. 모드 A와 구조 QC (2~3주)

**목표:** 시드를 고르면 후보를 생성하고, 구조를 예측해 pLDDT와 RMSD로 걸러내는 흐름을 CLI와 최소 UI로 끝까지 돌린다. 이 마일스톤이 v1에서 가장 길고 위험하며, 끝나면 "시드 → 후보 → 필터" end-to-end가 동작해야 한다.

- 관련 요구사항: F-1, F-3, F-5, F-7, F-13, F-17
- 선행 조건: M0 완료 (환경, 시드, 기준선)
- 공통 규약: [00-conventions.md](00-conventions.md)

## 작업 항목

| ID | 작업 | 요구사항 | 산출물 |
| --- | --- | --- | --- |
| M1-1 | 입출력. FASTA, PDB 파서, 시드 로더, IBS 번호 변환과 검증 | F-2, F-3 | `afp/io/` |
| M1-2 | 실행기. 서브프로세스 실행, `status.json` 갱신, 로그 기록, 취소 | F-13 | `afp/runner/` |
| M1-3 | 모드 A 설계. 아래 알고리즘 참고 | F-5 | `afp/design/mode_a.py` |
| M1-4 | 구조 QC. ESMFold 배치 예측, pLDDT, 시드 대비 RMSD, 캐시 | F-7 | `afp/evaluate/structure_qc.py` |
| M1-5 | 재현성 기록. `params.json`, `versions.json` 작성과 `rerun` 명령 | F-17 | `afp/runner/`, `afp/cli.py` |
| M1-6 | CLI. `design`, `evaluate`, `rerun` | F-1 | `afp/cli.py` |
| M1-7 | 최소 UI. 설계 실행 페이지와 실행 이력 페이지 | F-1, F-13 | `app/Home.py`, `app/pages/1_Runs.py` |
| M1-8 | 테스트. 불변식 property 테스트, 가짜 모델 통합 테스트, GPU 테스트 | 전체 | `tests/` |

## 모드 A 알고리즘 (M1-3)

v1은 **치환만** 지원한다. 삽입과 결실은 다루지 않으므로 후보 길이는 항상 시드와 같고, 시드 대비 RMSD를 위치별로 바로 계산할 수 있다.

1. **변이 가능 위치 결정.** 전체 위치에서 IBS 고정 잔기를 뺀다. 필요하면 사용자가 추가로 고정할 위치를 지정할 수 있다.
2. **IBS 근처 보수적 제한.** 시드 구조에서 IBS 잔기와 `near_ibs_angstrom`(기본 5 Å, 제안값) 이내에 있는 잔기는 같은 성질의 아미노산으로만 치환한다. 그룹 예: {A,V,I,L,M}, {F,Y,W}, {K,R,H}, {D,E}, {S,T,N,Q}. G, P, C는 치환 대상에서 제외한다.
3. **ESM-2 위치별 점수.** 변이 가능 위치마다 그 위치를 마스킹한 뒤, 아미노산별 `log p(aa) − log p(시드 아미노산)`를 계산한다(masked marginal). 위치 수만큼 배치로 한 번에 계산한다.
4. **후보 샘플링.** 체인마다 변이 개수 `k`를 1~`max_mutations`에서 균등하게 뽑고, **정확히 k개 변이를 가진 상태** 위에서 Metropolis MCMC를 돈다(기본 200 step). 제안은 (a) 같은 위치의 아미노산 교체, (b) 변이 위치를 다른 위치로 이동의 두 가지이며 둘 다 대칭이라 수락 확률은 `min(1, exp(Δ점수/T))`다. 점수는 위치별 masked marginal 로그비 `log p(변이 aa) − log p(시드 aa)`의 합(위치 간 독립 가정)이다. 체인마다 난수 시드를 `[rng_seed, 체인 번호]`로 정하고, 후보 `n_candidates`개를 모을 때까지(최대 30×n회 시도) 반복한다. 이전 문서의 "ESM 선호 변이를 쌓는" 방식은 야생형이 대부분 최선이라 변이가 거의 0개로 수렴해, 개수를 고정하는 방식으로 바꿨다.
5. **중복 제거.** 완전히 같은 서열은 제거한다. 서열 길이가 같으므로 해밍 거리 기준으로 너무 비슷한 후보도 거를 수 있다(MMseqs2는 v1에서 필수 아님).

**설계 결정:** 최적화 루프의 목적함수는 ESM 점수 하나만 쓴다. IBS 지표와 AFP 유사도는 루프 밖에서 생성 후 평가하고 순위를 매긴다(M2). 루프 안에 여러 목적을 넣는 다목적 최적화는 v1.x로 미룬다.

## 구조 QC (M1-4)

- 후보 서열을 ESMFold로 예측하고 구조는 서열 해시와 모델 버전을 키로 `cache/`에 저장한다. 같은 서열은 다시 예측하지 않는다.
- pLDDT는 0~100으로 통일한다. 모델 출력 단위를 M0에서 확인한 값에 맞춰 변환한다. 전체 평균(`plddt_mean`)과 IBS 영역 평균(`plddt_ibs`)을 모두 기록한다.
- RMSD는 시드의 실험 구조와 후보 예측 구조를 Cα 기준으로 겹쳐 구한다. 실험 구조에 없는 잔기(결손)는 교집합만 비교한다.
- 기본 임계값은 `pLDDT ≥ 80`, `RMSD ≤ 2 Å`(PRD 제안값)이며, M0-8 기준선을 보고 시드별로 조정할 수 있게 `config.py`와 UI에서 바꿀 수 있게 한다.
- 긴 서열에서 메모리 부족이 나면 배치 크기를 줄이거나 chunk size를 낮춰 재시도하고, 그래도 실패한 후보는 `failed`로 기록하고 계속 진행한다.

## 실행기 (M1-2)

- UI와 CLI는 같은 `run_design(params)`를 호출하되, UI는 서브프로세스(`python -m afp.cli design ...`)로 실행한다.
- 서브프로세스는 단계가 끝날 때마다 `status.json`을 갱신한다. 예외가 나면 `state=failed`와 `error`를 남기고 종료한다.
- 취소는 프로세스 트리를 종료하고 `cancelled`로 표시한다. 부분 결과는 폴더에 남긴다.
- 동시 실행 수는 설정값으로 제한한다(기본 1, GPU 하나 기준).
- Streamlit은 화면을 다시 그릴 때마다 `status.json`을 읽는다. 자동 갱신은 `st.fragment` 또는 수동 새로고침 버튼 중 간단한 쪽을 쓴다.

## 최소 UI (M1-7)

- **설계 실행 페이지:** 시드 선택(또는 FASTA/PDB 업로드와 IBS 번호 입력), `n_candidates`, `max_mutations`, 난수 시드, 실행 버튼, 진행률과 로그.
- **실행 이력 페이지:** `runs/` 목록, 상태, 파라미터 요약, 후보 표(pLDDT, RMSD 필터), 같은 설정으로 재실행.

## 테스트 (M1-8)

| 종류 | 내용 |
| --- | --- |
| property | 어떤 후보에서도 IBS 고정 잔기와 근처 제한 규칙이 지켜진다. 길이는 시드와 같다. 변이 수는 `max_mutations` 이하다 |
| unit | IBS 번호 변환, FASTA/PDB 파서의 오류 처리, 아미노산 그룹 제한 |
| integration | 가짜 ESM과 가짜 ESMFold로 N=5 end-to-end, `status.json` 전이, 취소 |
| 재현성 | 같은 `params.json`으로 재실행하면 `sequences.fasta`가 동일 |
| gpu | 실제 모델로 시드 하나, N=10 실행해 pLDDT와 RMSD가 채워지는지 |

## 수용 기준

- [ ] Type III 시드로 후보 100개를 CLI와 UI 양쪽에서 끝까지 생성·평가한다(F-5, F-7, F-13).
- [ ] 실행 폴더에 `params.json`, `versions.json`, `status.json`, `candidates.csv`가 남고 `rerun`으로 같은 서열이 재현된다(F-1, F-17).
- [ ] pLDDT와 RMSD 임계값을 바꿔 후보를 필터링할 수 있다.
- [ ] 취소와 실패가 UI에 올바르게 표시된다.
- [ ] 후보 중 `pLDDT ≥ 80`이면서 `RMSD ≤ 2 Å`인 비율이 얼마인지 시드별로 기록한다(PRD 성공 지표 30%의 기준 자료).

## 위험과 결정 사항

| 위험 | 대응 |
| --- | --- |
| ESM 점수만으로는 AFP 활성과 무관한 변이가 많이 나옴 | 의도된 단순화. M2의 IBS 지표와 순위로 걸러 보고, 부족하면 v1.x에서 루프에 목적을 추가 |
| 후보 대부분이 pLDDT 임계값 미만 | 시드별 임계값 정책을 적용하고 `max_mutations`를 낮춰 재시도. 비율을 기준선과 함께 기록 |
| ESMFold가 GPU 시간을 많이 씀 | 캐시 활용, 동시 실행 1개, 후보 수 기본값 조정 |
| Streamlit 새로고침으로 실행 상태를 잃음 | 상태는 항상 파일에서 읽는다. 세션 상태에 의존하지 않는다 |

## 열린 문제 (작성 후 채운다)

- `near_ibs_angstrom`, `temperature`, `max_mutations` 기본값의 근거:
- 임계값 통과 비율(시드별):
- ESMFold 실패 후보 처리 정책의 실제 사례:


## 구현 기록 (2026-10-12)

**구현 범위:** F-1, F-3, F-5, F-7, F-13, F-17 전부와 시드 등록(시나리오 2).

| 구성 | 파일 | 비고 |
| --- | --- | --- |
| 입출력 | `afp/io/{fasta,pdb,seeds}.py` | FASTA/PDB 파서, IBS 번호 변환(문헌 번호 + `residue_offset`), `create_seed`(PDB 업로드 또는 FASTA + ESMFold 예측) |
| 실행기 | `afp/runner/{status,launcher}.py` | `status.json` 원자적 쓰기, 서브프로세스 시작·취소(psutil로 프로세스 트리 종료), 동시 실행 한도, 죽은 프로세스는 `failed`로 정리 |
| 설계 | `afp/design/mode_a.py` | 위 알고리즘. 변이 가능 위치는 IBS·Gly·Pro·Cys 제외, IBS 반경 안은 보수적 치환만, 새 Cys 금지 |
| 구조 QC | `afp/evaluate/structure_qc.py` | ESMFold, 서열 해시 캐시, pLDDT, Kabsch RMSD, 개별 실패 기록 후 계속 진행 |
| 파이프라인·CLI | `afp/pipeline.py`, `afp/cli.py` | `design`, `evaluate`, `rerun`, `export`, `validate`, `seeds` |
| UI | `app/Home.py`, `app/pages/1_Runs.py` | 설계 실행(`st.fragment`로 2초마다 상태 폴링), 이력, 임계값 필터, 재실행, 취소 |

**검증**

- 실제 모델(ESM-2 GPU, ESMFold CPU)로 Type III 시드 후보 8개 end-to-end 실행: 모델 로딩 포함 약 100초, 8개 모두 구조 예측 성공(pLDDT 86~94, RMSD 0.69~2.9 Å).
- 자동 테스트: 불변식 property 테스트(모든 시드에서 IBS 고정, 길이 동일, 변이 수 ≤ 최대, Gly/Pro/Cys 위치 불변, 새 Cys 없음, IBS 근처는 보수적 치환만), 재현성(같은 `params.json` → 같은 `sequences.fasta`), 서브프로세스 실행·취소·실패·동시 실행 한도, 상태 파일이 반쯤 쓰이지 않음.

## 열린 문제 (답)

- `near_ibs_angstrom`(5 Å), `temperature`(1.0), `max_mutations`(8) 기본값의 근거: 모두 제안값이다. 5 Å는 IBS 잔기 측쇄 접촉 반경 정도로 잡았고, 후보 품질 비율([regression-baseline.md](regression-baseline.md))이 PRD 목표를 넘어 조정하지 않았다. 민감도 분석은 하지 않았다.
- 임계값 통과 비율(시드별, 후보 20개, 최대 변이 8): TmAFP 100%, Type I 95%, Type III 65%. PRD 목표(30% 이상)를 모두 넘는다.
- ESMFold 실패 후보 처리 정책의 실제 사례: 실제 모델 실행에서 실패는 없었다. 실패가 나면 `qc_status`에 원인을 기록하고 나머지를 계속 진행하는 동작은 가짜 예측기로 검증했다.
