# 환경 보고서 (python -m afp.check)

- Python 3.11.9 · Windows-10-10.0.26200-SP0
- torch 2.6.0+cu124 · transformers 5.19.0 · biopython 1.88
- GPU: NVIDIA GeForce RTX 3050 (6.0 GB)

| 항목 | 결과 | 내용 | 시간(s) |
| --- | --- | --- | --- |
| Python | ok | 3.11.9 | 0.0 |
| 패키지 | ok | torch 2.6.0+cu124, transformers 5.19.0, Bio 1.88, numpy 2.4.6, streamlit 1.65.0 | 3.2 |
| GPU | ok | NVIDIA GeForce RTX 3050, VRAM 6.0 GB, CUDA 12.4 | 0.0 |
| 시드·대조군 | ok | 시드 3개(tmafp_beetle, type1_hplc6, type3_hplc12), 음성 대조 3개 | 0.0 |
| FASTA/PDB 입출력 | ok | FASTA/PDB 왕복 일치 | 0.0 |
| SASA | ok | SASA 합 2955 Å^2 (Shrake-Rupley) | 0.1 |
| ESM-2 | ok | ESM-2 650M on cuda, masked marginal 3위치 0.32s | 6.8 |
| ESMFold | ok | ESMFold on cpu (VRAM 6.0GB < 14.0GB 이므로 cpu에서 실행): 로딩 5s, 37잔기 예측 7.1s, 평균 pLDDT 97.2 | 13.2 |
