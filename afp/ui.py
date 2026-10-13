"""Streamlit 페이지가 공유하는 도우미. 계산 로직은 넣지 않고 afp의 함수를 호출만 한다."""
from __future__ import annotations

import json
from pathlib import Path

from afp import config
from afp.io.pdb import align_to_reference, ca_coords, parse_pdb, write_pdb
from afp.io.seeds import Seed

EVIDENCE_LABEL = {
    "literature": "문헌 확인",
    "literature_partial": "문헌 일부 확인",
    "derived": "서열·구조로 유도(문헌 미확인)",
    "user_provided": "사용자 입력",
    "unverified": "미확인",
}
STATE_LABEL = {"queued": "대기", "running": "실행 중", "done": "완료", "failed": "실패", "cancelled": "취소됨"}
STAGE_LABEL = {"design": "설계", "structure_qc": "구조 예측·QC", "ibs_metrics": "IBS 지표", "scoring": "점수", "export": "내보내기"}
MODEL_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd"]


def validation_summary() -> dict | None:
    p = config.ROOT / "docs" / "dev" / "validation-report.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def show_disclaimer(st) -> None:
    st.warning(config.DISCLAIMER, icon="⚠️")


def show_validation_banner(st) -> None:
    v = validation_summary()
    if not v:
        st.caption("IBS 지표 양성 대조 검증 결과가 아직 없습니다 (`python -m afp.cli validate`).")
        return
    s = v["summary"]
    text = (f"IBS 지표 양성 대조 검증(예비): **{s['verdict']}** (시드 {s['seeds_passed']}/{s['seeds_total']}개 통과). "
            "평면성 지표는 시드와 무작위 패치를 구분했지만 면적·격자 편차는 일관되지 않았습니다. "
            "점수는 구조 신뢰도와 ESM 점수의 영향이 크므로 후보 선별용 보조 지표로만 사용하세요.")
    (st.success if s["verdict"] == "합격" else st.info)(text)


def seed_label(seed: Seed) -> str:
    return f"{seed.name} · {seed.length}aa · IBS {len(seed.ibs_residues)}개 · {EVIDENCE_LABEL.get(seed.ibs_evidence_level, seed.ibs_evidence_level)}"


def viewer_html(seed: Seed, candidates: list[tuple[str, str]], height: int = 520) -> str:
    """시드(회색)와 후보(색)를 Cα로 겹쳐 보여주는 py3Dmol HTML. IBS 잔기는 스틱으로 강조한다."""
    import py3Dmol

    seed_res = seed.residues()
    ref = ca_coords(seed_res)
    view = py3Dmol.view(width="100%", height=height)
    view.addModel(write_pdb(seed_res, "A"), "pdb")
    view.setStyle({"model": 0}, {"cartoon": {"color": "#b8b8b8", "opacity": 0.75}})
    view.addStyle({"model": 0, "resi": seed.ibs_pdb_numbers}, {"stick": {"color": "#555555", "radius": 0.18}})
    for i, (_, pdb_text) in enumerate(candidates, start=1):
        aligned = align_to_reference(parse_pdb(pdb_text, "A"), ref)
        view.addModel(write_pdb(aligned, "A", renumber=True), "pdb")
        color = MODEL_COLORS[(i - 1) % len(MODEL_COLORS)]
        view.setStyle({"model": i}, {"cartoon": {"color": color}})
        view.addStyle({"model": i, "resi": [idx + 1 for idx in seed.ibs_indices]}, {"stick": {"color": color, "radius": 0.2}})
    view.zoomTo()
    return view._make_html()


def short_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def run_dir_of(run_id: str) -> Path:
    return config.RUNS_DIR / run_id
