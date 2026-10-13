# 시드 기준선 (M0-8)

시드 서열을 ESMFold(`facebook/esmfold_v1`, cpu)로 예측해 실험 구조와 비교한 값이다. 이 값은 M1의 pLDDT·RMSD 임계값을 시드별로 조정할 때의 근거 자료다.

- 환경: Windows-10-10.0.26200-SP0, torch 2.6.0+cu124, transformers 5.19.0
- 장치: cpu (VRAM 6.0GB < 14.0GB 이므로 cpu에서 실행)

| 시드 | 길이 | 근거 수준 | 평균 pLDDT | IBS 영역 pLDDT | 실험 구조 대비 RMSD (Å) | 예측 시간 (s) |
| --- | --- | --- | --- | --- | --- | --- |
| tmafp_beetle | 82 | literature_partial | 93.6 | 95.9 | 0.76 | 19 |
| type1_hplc6 | 37 | derived | 97.2 | 97.4 | 0.79 | 4 |
| type3_hplc12 | 66 | literature | 94.3 | 96.9 | 0.72 | 10 |

임계값(pLDDT ≥ 80, RMSD ≤ 2 Å)과 비교해 시드 자체가 통과하는지 확인한다. 통과하지 못하는 시드는 시드별 임계값을 따로 둔다.
