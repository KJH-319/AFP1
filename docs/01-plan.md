# 부동 단백질(Antifreeze Protein, AFP) 디자인 앱 — 계획 문서

> **참고:** 이 문서는 초기 계획(풀 스코프)이다. 이후 오버엔지니어링을 줄여 v1 범위를 슬림화했으며, 최신 범위와 일정은 [02-PRD.md](02-PRD.md)를 기준으로 한다. 모드 B(de novo), 간이 MD, 분류기 학습, 실험 결과 업로드는 v1.x로 미뤘고 일정은 12~17주에서 5~7주로 줄었다.

## 1. Context (배경과 목적)

**문제**: 부동 단백질(AFP)은 얼음 결정 표면에 결합해 성장을 억제(열이력 Thermal Hysteresis, TH)하고 재결정을 막는다. 냉동보존, 냉동식품, 장기 보존, 저온 내성 작물 등에 쓰이지만, 천연 AFP는 종류가 제한적이고 활성·안정성·생산성이 최적이 아니다. 새 AFP를 설계하려면 서열/구조 모델링, 얼음 결합면(IBS) 설계, 구조 예측, 활성 평가를 여러 도구에 걸쳐 수작업으로 해야 한다.

**목표**: 연구자가 (1) 기존 AFP를 시작점으로 삼거나 (2) IBS 모티프를 지정해 de novo로 새 AFP 후보를 생성하고, (3) 구조 신뢰도·AFP 가능성·간이 MD 결과로 순위를 매겨, (4) 실험 검증용 후보 목록(서열/구조/보고서)을 내보내는 **연구실 내부용 웹앱**을 만든다.

**확정된 결정사항** (사용자 답변):
| 항목 | 결정 |
|---|---|
| 사용자/배포 | 연구실 내부용 웹앱 (소수 연구자, GPU 서버 1대 또는 클라우드 GPU) |
| 디자인 방식 | 하이브리드 (서열 기반 변이/ESM + 구조 기반 de novo) |
| 평가 범위 | ML 스코어 + 간이 MD (선택적) |
| UI 스택 | Streamlit 또는 Gradio (프로토타입 속도 우선) |

> 참고: 작업 폴더가 비어 있으므로 신규 프로젝트(greenfield)다. 재사용할 기존 코드는 없고, 외부 오픈소스 도구를 래핑하는 구조로 간다.

---

## 2. 사용자 워크플로우 (앱 기능)

1. **프로젝트 생성** — 목표 설정 (예: "Type III 계열 TH 향상", "IBS 지정 de novo 5개 후보").
2. **입력 선택**
   - A. *시드 AFP 선택*: 내장 AFP 라이브러리(Type I/II/III/IV, AFGP, 곤충 β-helix(TmAFP, sbwAFP), 식물/박테리아 DUF3494)에서 선택 또는 UniProt/PDB ID, FASTA, PDB 업로드.
   - B. *IBS 모티프 지정(de novo)*: 얼음 결합면 잔기 패턴(예: Thr-X-Thr 반복, 평면 친수/소수 격자)과 길이·접힘 토폴로지를 지정.
3. **디자인 실행** — 모드 선택 후 후보 N개 생성 (비동기 작업).
4. **필터/평가** — 자동 스코어링, 순위표, 3D 비교.
5. **간이 MD (선택)** — 상위 K개에 대해 얼음 표면 결합 시뮬레이션.
6. **내보내기** — FASTA, PDB, CSV 순위표, PDF/Markdown 리포트, 실험 프로토콜 권고(발현 벡터 힌트, 코돈 최적화 선택).

---

## 3. 디자인 파이프라인

### 3.1 모드 A — 서열 기반 최적화 (시드 있음)
- **IBS 보존 마스킹**: 시드 구조에서 IBS 잔기 식별(문헌/PDB 주석 + 구조 기반 평면성 분석)해 고정(fix).
- **변이 제안**: ESM-2/ESM-IF1 로그우도로 비-IBS 위치 변이 제안; IBS 주변은 소규모 보수적 변이만 허용.
- **최적화 루프**: 유전알고리즘 또는 MCMC로 (AFP 점수 + 안정성 + 용해성) 목적함수를 최대화.
- 도구: `fair-esm` / ESM-IF1, 필요 시 ProteinMPNN(고정 잔기 지정).

### 3.2 모드 B — 구조 기반 de novo
- **Backbone 생성**: RFdiffusion(motif scaffolding)으로 IBS 모티프를 고정한 채 주변 골격 생성. 대안: 곤충 AFP식 β-solenoid, α-helical bundle, 폴리프롤린 II형 토폴로지를 템플릿으로 사용.
- **서열 설계**: ProteinMPNN(IBS 잔기 고정, 표면 용해성 편향).
- **구조 검증(refolding)**: ColabFold/AlphaFold2 또는 ESMFold로 재예측 → 설계 backbone과 RMSD, pLDDT, pAE 확인 (self-consistency).
- 도구: RFdiffusion, ProteinMPNN, ColabFold(로컬), ESMFold.

### 3.3 공통 후처리
- 중복 제거(서열 클러스터링, MMseqs2), 다양성 확보.
- 개발성 필터: 순전하·pI, 소수성 패치, 글리코실화/절단 모티프, 발현 숙주(E. coli/Pichia) 적합성.

---

## 4. 평가·스코어링

| 단계 | 지표 | 도구 | 비고 |
|---|---|---|---|
| 구조 신뢰도 | pLDDT, pAE, 설계-예측 RMSD | ColabFold/ESMFold | 하드 필터 (예: pLDDT>80) |
| AFP 가능성 | 확률 점수 | 공개 AFP 예측기(AFP-Pred 계열) 또는 자체 학습 분류기 | 자체 모델은 6장 참고 |
| IBS 품질 | 평면성, 결합면 면적, 규칙적 격자 간격(~4.5/7.35 Å 정합), 소수성 비율 | 자체 구조 분석(Biopython/MDAnalysis/freesasa) | 핵심 차별 지표 |
| 안정성 | ΔΔG 근사, 인터페이스 소수성 | FoldX/Rosetta(라이선스 확인) 또는 ESM 기반 대체 | 라이선스 이슈 시 대체 |
| 간이 MD | 얼음 prism/basal면 결합 지속 시간, 결합 에너지, IBS-얼음 수소결합 수 | GROMACS/OpenMM + TIP4P/Ice + 얼음 슬랩 | 상위 K개만, GPU 시간 제한 |

- **종합 점수**: 가중합(사용자가 UI에서 가중치 조절) + Pareto 순위. 점수는 **우선순위 보조 지표**이며 실제 TH는 예측하지 못함을 UI에 명시.

---

## 5. 시스템 아키텍처 (Streamlit/Gradio 기반)

```
[Streamlit/Gradio UI]  ── 입력/결과/3D 뷰어(py3Dmol 또는 stmol)
        │
[Service layer (Python 모듈)]  ── 파이프라인 오케스트레이션
        │
[Job runner: 로컬 서브프로세스 큐 (RQ/Celery 중 단순한 것)]
        ├─ design/   : mode_a_seq.py, mode_b_denovo.py
        ├─ evaluate/ : structure_qc.py, ibs_metrics.py, afp_classifier.py, developability.py
        ├─ md/       : build_ice_system.py, run_md.py, analyze_md.py
        └─ export/   : report.py
        │
[저장소: SQLite(메타데이터) + 파일시스템(PDB/FASTA/trajectory)]
[모델 가중치/도구: Docker 이미지 or conda 환경 (RFdiffusion, ProteinMPNN, ColabFold, GROMACS)]
```

설계 원칙:
- **무거운 작업은 UI 프로세스와 분리**(Streamlit 재실행 모델 때문에 장시간 작업을 UI 안에서 돌리지 않음). 작업 ID로 진행률/로그 폴링.
- 각 외부 도구는 **어댑터 인터페이스**(`DesignBackend`, `StructurePredictor`, `Scorer`)로 감싸 교체 가능하게 한다.
- 모든 실행은 **재현성 메타데이터**(시드, 버전, 파라미터)를 DB에 기록.
- 권장 디렉터리:
```
afp-designer/
  app/            # Streamlit/Gradio 페이지
  afp/            # 코어 파이프라인 패키지 (design, evaluate, md, export)
  data/seeds/     # 큐레이션된 AFP 시드 라이브러리 (PDB/UniProt ID, IBS 주석)
  docker/ envs/   # 도구별 환경
  tests/
  docs/
```

---

## 6. 데이터와 모델

- **시드 라이브러리**: PDB/UniProt에서 AFP 큐레이션 (Type I: 1WFA, Type III: 1HG7, 곤충 TmAFP: 1EZG 등 — *ID는 구현 시 실제 확인*). 각 항목에 IBS 잔기 주석 수동 검증.
- **학습/평가 데이터(분류기용)**: UniProt AFP 어노테이션 + 공개 AFP 데이터셋을 양성, 길이/조성 매칭된 비-AFP를 음성으로. 서열 유사도 기반 train/test 분리(MMseqs2 30% 컷)로 누수 방지.
- **분류기**: ESM-2 임베딩 + 로지스틱 회귀/경량 MLP (작은 데이터에 적합). 외부 예측기가 쓸 만하면 어댑터로 병용.
- **한계 명시**: TH 값의 공개 정량 데이터가 적어 회귀 예측은 MVP에서 제외.

---

## 7. 단계별 로드맵

| 단계 | 내용 | 산출물 | 대략 기간 |
|---|---|---|---|
| M0 | 환경 구축(GPU, conda/Docker), 도구 설치 검증, 시드 라이브러리 큐레이션 | 도구별 smoke test, 시드 20~30개 | 1~2주 |
| M1 | 모드 A(서열 최적화) + 구조 QC + 순위표 + Streamlit UI 뼈대 | 시드→후보→순위표 end-to-end | 2~3주 |
| M2 | 모드 B(RFdiffusion→MPNN→ColabFold) + IBS 지표 | de novo 후보 생성 | 3~4주 |
| M3 | AFP 분류기, 개발성 필터, 종합 점수/Pareto, 3D 뷰어 | 평가 대시보드 | 2주 |
| M4 | 간이 MD(얼음 슬랩 빌더, OpenMM/GROMACS 자동화) | 상위 K개 MD 리포트 | 3~4주 |
| M5 | 내보내기/리포트, 문서화, 실험 피드백 루프(결과 업로드) | v1.0 | 1~2주 |

---

## 8. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| **in silico 점수가 실제 TH와 불일치** | 점수를 "후보 우선순위"로만 표기, 실험 결과 업로드 기능(M5)으로 점수 보정 |
| 반복 구조/저복잡도 AFP를 ESM/AF가 잘 못 다룸 | 곤충 β-helix 등은 템플릿 기반 모드 우선, 구조 신뢰도 임계값 완화 옵션 |
| MD 비용·시간 | 상위 K개만, 짧은 시뮬레이션(수십 ns), 결과 캐시, 작업 큐 동시성 제한 |
| 얼음-단백질 MD 설정 난이도 | 얼음 슬랩 템플릿 + 검증된 프로토콜 사용, 알려진 AFP(양성 대조)로 파이프라인 검증 |
| 도구 라이선스 (Rosetta, FoldX 등) | 오픈 라이선스 대체 경로 유지, 설치 시 라이선스 체크 문서화 |
| Streamlit 장시간 작업 한계 | 외부 작업 큐 + 폴링 구조 (5장) |
| 생물안전/이중용도 | AFP는 위험도 낮으나, 일반 단백질 설계 도구 사용 시 기관 정책·로그 보관 유지 |

---

## 9. 검증 계획 (Verification)

1. **도구 smoke test**: 각 외부 도구가 샘플 입력으로 동작 (CI 또는 `make check`).
2. **양성 대조(핵심)**: 알려진 AFP(Type III, TmAFP) 구조를 입력해 — 구조 QC 통과, IBS 지표가 비-AFP 대조(예: 무작위 단백질)보다 유의하게 높음, 간이 MD에서 얼음 결합이 관찰되는지 확인.
3. **de novo 회귀 테스트**: 고정 시드로 설계 → refold RMSD/pLDDT 분포가 기준선 이상인지 자동 검사.
4. **분류기 검증**: 서열 유사도 분리된 테스트셋에서 AUROC/AUPRC 측정, 리포트에 포함.
5. **UI end-to-end**: 시드 선택 → 설계 → 순위표 → 내보내기까지 수동 시나리오 + Streamlit AppTest 자동화.
6. **실험 검증(앱 밖)**: 상위 후보 5~10개를 발현 후 ice recrystallization inhibition(IRI, splat assay), nanoliter osmometer TH 측정 → 결과를 앱에 되먹임.

---

## 10. 다음 결정이 필요한 항목 (구현 착수 전)
- GPU 환경 사양(로컬 GPU 모델/VRAM, 또는 클라우드)과 설치 가능한 도구 범위
- 주 타깃 AFP 유형 및 응용(냉동보존/식품/작물) — 시드 큐레이션 우선순위 결정
- Streamlit vs Gradio 최종 선택 (3D 뷰어·다중 페이지가 중요하면 Streamlit 권장)