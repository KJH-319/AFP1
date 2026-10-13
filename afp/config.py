"""경로, 기본 파라미터, 임계값. 설정값은 모두 이 파일에 모은다."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SEEDS_DIR = DATA_DIR / "seeds"
CONTROLS_DIR = DATA_DIR / "controls"

# 실행 결과(runs), 캐시, 내보내기 위치. 프로젝트 경로가 깊으면 Windows 경로 한도(260자)를 넘기 쉬우므로
# 그때는 사용자 홈의 짧은 폴더를 쓴다. AFP_DATA_DIR 환경변수로 직접 지정할 수 있다.
LONG_PATH_LIMIT = 150


def _data_root() -> Path:
    if os.environ.get("AFP_DATA_DIR"):
        return Path(os.environ["AFP_DATA_DIR"])
    if len(str(ROOT)) > LONG_PATH_LIMIT:
        return Path.home() / "afp-data"
    return ROOT


DATA_ROOT = _data_root()
RUNS_DIR = Path(os.environ.get("AFP_RUNS_DIR", DATA_ROOT / "runs"))
CACHE_DIR = Path(os.environ.get("AFP_CACHE_DIR", DATA_ROOT / "cache"))
EXPORTS_DIR = Path(os.environ.get("AFP_EXPORTS_DIR", DATA_ROOT / "exports"))

AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"

ESM_MODEL = "facebook/esm2_t33_650M_UR50D"
STRUCTURE_MODEL = "facebook/esmfold_v1"

DISCLAIMER = "우선순위 보조 지표이며 실제 TH(열이력) 예측이 아닙니다."

# 시드 IBS 근거 수준. unverified는 로더가 기본적으로 거부한다.
EVIDENCE_LEVELS = ("literature", "literature_partial", "derived", "user_provided", "unverified")

# 구조 QC 임계값 (PRD 제안값, 시드별로 UI에서 조정 가능)
PLDDT_MIN = 80.0
RMSD_MAX = 2.0

# 모드 A
NEAR_IBS_ANGSTROM = 5.0
MCMC_STEPS = 200
CONSERVATIVE_GROUPS = ("AVILM", "FYW", "KRH", "DE", "STNQ")
FROZEN_WILDTYPE = "GPC"          # 이 아미노산 위치는 변이시키지 않는다
FORBIDDEN_TARGETS = "C"           # 새로 도입하지 않는 아미노산

# IBS 지표
ICE_LATTICE_SPACINGS = (4.52, 7.35)   # a축, c축 간격 (Å, 제안값)
LATTICE_MAX_MULTIPLE = 2
LATTICE_PAIR_MIN = 3.0                # 이보다 가까운 원자 쌍은 제외
LATTICE_PAIR_MAX = 10.0               # 이보다 먼 쌍은 제외
HYDROPHOBIC = "AVLIMFWC"
RANDOM_PATCH_COUNT = 100
SURFACE_REL_SASA = 0.2                # 표면 잔기 판정(상대 SASA)

# 종합 점수 (그룹별 가중치, 합 1로 정규화) 와 그룹 정규화 상수
DEFAULT_WEIGHTS = {"structure": 0.3, "ibs": 0.4, "afp": 0.2, "dev": 0.1}
PLDDT_NORM_LO = 50.0                  # 이 값 이하면 0점
PLDDT_NORM_HI = 90.0                  # 이 값 이상이면 1점
RMSD_NORM_MAX = 4.0                   # RMSD가 이 값이면 0점 (0 Å이면 1점)
IBS_NORM_CAP = 1.2                    # 시드 IBS 값을 넘어서도 최대 1.2까지만 인정
LLR_PER_MUTATION_SCALE = 4.0          # 변이당 평균 로그비 +-2 가 0~1 범위
DEV_FLAG_PENALTY = 0.25               # 개발성 플래그 하나당 감점

# 개발성
HYDROPHOBIC_PATCH_DELTA = 0.10        # 시드보다 노출 소수성 SASA 비율이 이만큼 늘면 플래그
DUPLICATE_IDENTITY = 0.97

# 구조 예측 최대 후보 길이 (ESMFold 메모리 보호)
MAX_SEQUENCE_LENGTH = 400

DEFAULT_PARAMS = {
    "seed_id": "type3_hplc12",
    "n_candidates": 100,
    "max_mutations": 8,
    "near_ibs_angstrom": NEAR_IBS_ANGSTROM,
    "temperature": 1.0,
    "mcmc_steps": MCMC_STEPS,
    "rng_seed": 1,
    "esm_model": ESM_MODEL,
    "structure_model": STRUCTURE_MODEL,
    "backend": "real",               # real | mock
    "device": "auto",                # auto | cuda | cpu
    "plddt_min": PLDDT_MIN,
    "rmsd_max": RMSD_MAX,
    "weights": DEFAULT_WEIGHTS,
    "evaluate": True,
}


def ensure_dirs() -> None:
    for d in (RUNS_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
