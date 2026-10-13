"""ESM-2(변이 점수)와 ESMFold(구조 예측) 백엔드, 그리고 테스트용 가짜(mock) 백엔드.

외부 도구 호출은 이 모듈 한 곳에 모은다. 두 번째 도구가 필요해지기 전에는 추상화하지 않는다.
"""
from __future__ import annotations

import hashlib
import os
import platform
import sys
from dataclasses import dataclass

import numpy as np

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from afp.config import AMINO_ACIDS, ESM_MODEL, STRUCTURE_MODEL
from afp.io.pdb import ONE_TO_THREE, Residue, parse_pdb, write_pdb

_AA_INDEX = {a: i for i, a in enumerate(AMINO_ACIDS)}


@dataclass
class Prediction:
    pdb_text: str          # B-factor 열에 pLDDT(0~100)
    plddt: np.ndarray      # 잔기별 pLDDT, 0~100


def _seed_from(*parts) -> int:
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:12], 16)


def resolve_device(device: str = "auto") -> str:
    import torch

    if device == "cpu":
        return "cpu"
    if device == "cuda" or device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    raise ValueError(f"알 수 없는 device: {device}")


# ---------------------------------------------------------------- 실제 ESM-2

class EsmScorer:
    """ESM-2 masked marginal. 위치를 마스킹하고 20개 아미노산의 로그확률을 구한다."""

    def __init__(self, model_name: str = ESM_MODEL, device: str = "auto", batch_size: int = 16):
        import torch
        from transformers import AutoTokenizer, EsmForMaskedLM

        self.model_name = model_name
        self.device = resolve_device(device)
        self.batch_size = batch_size
        self.tok = AutoTokenizer.from_pretrained(model_name)
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        try:
            model = EsmForMaskedLM.from_pretrained(model_name, dtype=dtype)
        except TypeError:  # 구버전 transformers
            model = EsmForMaskedLM.from_pretrained(model_name, torch_dtype=dtype)
        self.model = model.to(self.device).eval()
        self._aa_ids = [self.tok.convert_tokens_to_ids(a) for a in AMINO_ACIDS]

    def masked_marginals(self, seq: str, positions: list[int]) -> np.ndarray:
        """(len(positions), 20) 로그확률. 20개 아미노산 위에서 재정규화한다."""
        import torch

        if not positions:
            return np.zeros((0, 20), dtype=np.float32)
        base = self.tok(seq, return_tensors="pt")["input_ids"][0]
        mask_id = self.tok.mask_token_id
        out = []
        for start in range(0, len(positions), self.batch_size):
            chunk = positions[start : start + self.batch_size]
            batch = base.unsqueeze(0).repeat(len(chunk), 1)
            for row, pos in enumerate(chunk):
                batch[row, pos + 1] = mask_id  # +1: CLS 토큰
            with torch.no_grad():
                logits = self.model(input_ids=batch.to(self.device)).logits.float()
            rows = torch.arange(len(chunk), device=logits.device)
            at = logits[rows, torch.tensor([p + 1 for p in chunk], device=logits.device)]
            sub = at[:, self._aa_ids]
            out.append(torch.log_softmax(sub, dim=-1).cpu().numpy())
        return np.concatenate(out, axis=0).astype(np.float32)


# ---------------------------------------------------------------- 실제 ESMFold

class EsmFoldPredictor:
    """ESMFold(Hugging Face transformers 구현).

    VRAM이 부족하면(ESMFold fp16은 대략 14GB 이상 권장) 자동으로 CPU에서 실행한다.
    """

    MIN_VRAM_GB = 14.0

    def __init__(self, model_name: str = STRUCTURE_MODEL, device: str = "auto", chunk_size: int = 64):
        import torch
        from transformers import AutoTokenizer, EsmForProteinFolding

        self.model_name = model_name
        self.tok = AutoTokenizer.from_pretrained(model_name)
        model = EsmForProteinFolding.from_pretrained(model_name, low_cpu_mem_usage=True)
        model.eval()
        self.device = "cpu"
        self.note = ""
        want = resolve_device(device)
        if want == "cuda":
            total = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
            if device == "cuda" or total >= self.MIN_VRAM_GB:
                try:
                    model.esm = model.esm.half()
                    model = model.cuda()
                    self.device = "cuda"
                except RuntimeError as exc:  # OOM
                    model = model.float().cpu()
                    self.note = f"cuda 실패, cpu 사용: {str(exc)[:80]}"
            else:
                self.note = f"VRAM {total:.1f}GB < {self.MIN_VRAM_GB}GB 이므로 cpu에서 실행"
        model.trunk.set_chunk_size(chunk_size)
        self.model = model

    def predict(self, seq: str) -> Prediction:
        import torch

        ids = self.tok([seq], return_tensors="pt", add_special_tokens=False)["input_ids"].to(self.device)
        with torch.no_grad():
            out = self.model(ids)
        per_atom = out["plddt"][0].float().cpu().numpy()          # (L, 37) atom37
        per_res = per_atom[:, 1] if per_atom.ndim == 2 else per_atom  # CA(atom37 인덱스 1)
        if per_res.max() <= 1.5:                                    # 0~1 단위이면 0~100으로
            per_res = per_res * 100.0
        pdb = self.model.output_to_pdb(out)[0]
        residues = parse_pdb(pdb, None)
        if len(residues) != len(seq):
            raise RuntimeError(f"예측 구조의 잔기 수({len(residues)})가 서열 길이({len(seq)})와 다릅니다.")
        text = write_pdb(residues, chain="A", renumber=True, bfactor_per_residue=per_res)
        return Prediction(pdb_text=text, plddt=np.asarray(per_res, dtype=float))


# ---------------------------------------------------------------- 가짜(mock) 백엔드

class MockEsmScorer:
    """BLOSUM62 + 고정 난수로 그럴듯한 위치별 확률을 만든다. 테스트와 CI용."""

    model_name = "mock-esm"
    device = "cpu"

    def __init__(self):
        from Bio.Align import substitution_matrices

        self._blosum = substitution_matrices.load("BLOSUM62")

    def masked_marginals(self, seq: str, positions: list[int]) -> np.ndarray:
        out = np.zeros((len(positions), 20), dtype=np.float32)
        for row, pos in enumerate(positions):
            rng = np.random.default_rng(_seed_from(seq, pos))
            wt = seq[pos]
            logits = np.array([0.5 * self._blosum[wt][a] for a in AMINO_ACIDS]) + rng.normal(0, 0.5, 20)
            logits -= logits.max()
            out[row] = logits - np.log(np.exp(logits).sum())
        return out


class MockStructurePredictor:
    """시드 구조를 템플릿으로 약간의 잡음을 더해 '예측'한다. 변이 위치는 pLDDT가 낮아진다."""

    model_name = "mock-fold"
    device = "cpu"

    def __init__(self, template: list[Residue], template_seq: str, noise: float = 0.3, base_plddt: float = 88.0):
        self.template, self.template_seq = template, template_seq
        self.noise, self.base = noise, base_plddt

    def predict(self, seq: str) -> Prediction:
        if len(seq) != len(self.template_seq):
            raise ValueError("mock 예측기는 시드와 같은 길이의 서열만 지원합니다.")
        rng = np.random.default_rng(_seed_from("fold", seq))
        residues, plddt = [], np.zeros(len(seq))
        for i, tpl in enumerate(self.template):
            if seq[i] == self.template_seq[i]:
                atoms = {k: v.copy() for k, v in tpl.atoms.items()}
                plddt[i] = self.base + rng.normal(0, 2.0)
                name3 = tpl.name3
            else:
                keep = ("N", "CA", "C", "O") + (("CB",) if seq[i] != "G" else ())
                atoms = {k: v.copy() for k, v in tpl.atoms.items() if k in keep}
                plddt[i] = self.base - 10 + rng.normal(0, 3.0)
                name3 = ONE_TO_THREE[seq[i]]
            for k in atoms:
                atoms[k] = atoms[k] + rng.normal(0, self.noise, 3)
            residues.append(Residue(number=i + 1, name3=name3, atoms=atoms))
        plddt = np.clip(plddt, 20.0, 98.0)
        return Prediction(pdb_text=write_pdb(residues, "A", renumber=True, bfactor_per_residue=plddt), plddt=plddt)


# ---------------------------------------------------------------- 팩토리와 버전 정보

_REAL_CACHE: dict[tuple, object] = {}


def get_backends(params: dict, seed):
    """(scorer, predictor). params['backend']가 'mock'이면 가짜, 아니면 실제 모델."""
    if params.get("backend") == "mock":
        return MockEsmScorer(), MockStructurePredictor(seed.residues(), seed.sequence, base_plddt=params.get("mock_plddt", 88.0))
    key_s = ("esm", params["esm_model"], params.get("device", "auto"))
    key_p = ("fold", params["structure_model"], params.get("device", "auto"))
    if key_s not in _REAL_CACHE:
        _REAL_CACHE[key_s] = EsmScorer(params["esm_model"], params.get("device", "auto"))
    if key_p not in _REAL_CACHE:
        _REAL_CACHE[key_p] = EsmFoldPredictor(params["structure_model"], params.get("device", "auto"))
    return _REAL_CACHE[key_s], _REAL_CACHE[key_p]


def get_predictor(params: dict, template_seed=None):
    if params.get("backend") == "mock":
        if template_seed is None:
            raise ValueError("mock 예측기에는 템플릿 시드가 필요합니다.")
        return MockStructurePredictor(template_seed.residues(), template_seed.sequence)
    key_p = ("fold", params["structure_model"], params.get("device", "auto"))
    if key_p not in _REAL_CACHE:
        _REAL_CACHE[key_p] = EsmFoldPredictor(params["structure_model"], params.get("device", "auto"))
    return _REAL_CACHE[key_p]


def versions(params: dict | None = None) -> dict:
    """재현성 기록용 버전 정보 (versions.json)."""
    info: dict = {"python": sys.version.split()[0], "platform": platform.platform()}
    for mod in ("numpy", "pandas", "scipy", "Bio", "transformers", "torch", "streamlit"):
        try:
            m = __import__(mod)
            info[mod] = getattr(m, "__version__", "?")
        except Exception:  # noqa: BLE001
            info[mod] = None
    try:
        import torch

        info["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            info["gpu"] = p.name
            info["gpu_vram_gb"] = round(p.total_memory / 1024 ** 3, 1)
    except Exception:  # noqa: BLE001
        info["cuda_available"] = False
    if params:
        info["backend"] = params.get("backend")
        info["esm_model"] = params.get("esm_model")
        info["structure_model"] = params.get("structure_model")
    from afp import __version__

    info["afp"] = __version__
    return info
