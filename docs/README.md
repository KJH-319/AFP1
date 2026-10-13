# AFP Designer 문서

부동 단백질(Antifreeze Protein, AFP) 후보를 설계하고 평가하는 연구실 내부용 웹앱의 계획, 개발, 운영 문서 모음이다. 코드와 실행 방법은 저장소 루트의 [README.md](../README.md)에 있다.

## 읽는 순서

| 문서 | 내용 | 상태 |
| --- | --- | --- |
| [01-plan.md](01-plan.md) | 초기 계획(풀 스코프). 배경, 파이프라인, 아키텍처 아이디어 | 참고용. 범위는 PRD가 우선 |
| [02-PRD.md](02-PRD.md) | **제품 요구사항 (슬림 v1)**. 기능 요구사항 F-1~F-17, 일정, 리스크 | 최신 기준 |
| [user-guide.md](user-guide.md) | 사용자 가이드: 시나리오, 순위표 읽는 법, 플래그, 내보내기 | v1 |
| [ops.md](ops.md) | 운영: 설치 검증, 위치, GPU와 실행 시간, 문제 해결, 보안 | v1 |
| [dev/00-conventions.md](dev/00-conventions.md) | 저장소 구조, 작업 폴더 형식, CLI, 테스트 전략 | 개발 공통 규약 |
| [dev/M0-environment-seeds.md](dev/M0-environment-seeds.md) | M0 환경 구축과 시드 큐레이션 (구현 기록 포함) | 완료 |
| [dev/M1-mode-a-structure-qc.md](dev/M1-mode-a-structure-qc.md) | M1 모드 A와 구조 QC (구현 기록 포함) | 완료 |
| [dev/M2-ibs-metrics-ranking-ui.md](dev/M2-ibs-metrics-ranking-ui.md) | M2 IBS 지표와 순위표 UI (구현 기록 포함) | 완료 |
| [dev/M3-validation-export.md](dev/M3-validation-export.md) | M3 검증과 내보내기 (구현 기록 포함) | 완료(사용성 테스트 제외) |
| [dev/release-checklist.md](dev/release-checklist.md) | v1.0 출시 점검 결과 | |
| [dev/v1x-backlog.md](dev/v1x-backlog.md) | v1에서 미룬 항목과 착수 조건 | |

생성된 보고서: [env-report.md](dev/env-report.md) · [baseline.md](dev/baseline.md) · [validation-report.md](dev/validation-report.md) · [validation-report-predicted.md](dev/validation-report-predicted.md) · [regression-baseline.md](dev/regression-baseline.md)

## v1 범위 요약

- **포함:** 시드 기반 서열 최적화(모드 A), 구조 QC(ESMFold), IBS 지표, 개발성 필터, 순위표, 3D 뷰어, 내보내기
- **제외(v1.x):** de novo 설계(모드 B), 간이 MD, 분류기 학습, 실험 결과 업로드, Pareto, PDF 리포트
- **전제:** 점수는 우선순위 보조 지표이며 실제 열이력(TH)을 예측하지 않는다. 양성 대조 검증(예비)은 불합격이었다. 점수가 쓸모 있는지는 소수 후보의 실험으로 확인한다.

## 마일스톤 의존 관계

```
M0 환경·시드  →  M1 모드 A·구조 QC  →  M2 IBS 지표·순위표 UI  →  M3 검증·내보내기  →  (실험 결과)  →  v1.x
```

## 용어

| 용어 | 뜻 |
| --- | --- |
| AFP | Antifreeze Protein, 부동 단백질 |
| IBS | Ice-Binding Site, 얼음 결합면 |
| TH | Thermal Hysteresis, 열이력. 어는점과 녹는점의 차이로 나타나는 AFP 활성 |
| IRI | Ice Recrystallization Inhibition, 얼음 재결정 억제 |
| pLDDT | 구조 예측의 잔기별 신뢰도 (0~100) |
| 시드 | 설계의 출발점이 되는 기존 AFP |
| 모드 A / B | A는 시드 서열 최적화, B는 IBS 모티프에서 시작하는 de novo 설계(v1.x) |

## 문서 관리

- PRD는 Claude Docs의 "PRD: 부동 단백질(AFP) 디자인 앱"에서 작성했고 `02-PRD.md`는 그 스냅샷이다. 요구사항을 바꾸면 두 곳을 맞춘다.
- 각 마일스톤 문서의 "구현 기록"과 "열린 문제"는 구현 결과를 반영한다.
