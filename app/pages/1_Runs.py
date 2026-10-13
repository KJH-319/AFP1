"""실행 이력 페이지 (F-1, F-7, F-13, F-17).  후보 표와 pLDDT·RMSD 임계값 필터, 재실행."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from afp import config  # noqa: E402
from afp.evaluate.structure_qc import apply_thresholds  # noqa: E402
from afp.pipeline import load_candidates  # noqa: E402
from afp.runner import launcher  # noqa: E402
from afp.ui import STAGE_LABEL, STATE_LABEL, show_disclaimer  # noqa: E402

st.set_page_config(page_title="실행 이력 · AFP Designer", page_icon="🧊", layout="wide")
st.title("실행 이력")
show_disclaimer(st)

runs = launcher.list_runs()
if not runs:
    st.info("아직 실행 기록이 없습니다. 홈에서 설계를 실행해 보세요.")
    st.stop()

table = pd.DataFrame([{
    "실행": r["run_id"], "시드": r["seed_id"], "후보 수": r["n_candidates"], "백엔드": r["backend"],
    "상태": STATE_LABEL.get(r["state"], r["state"]), "진행률": float(r["progress"] or 0.0),
    "시작": r["started_at"], "오류": r["error"] or "",
} for r in runs])
event = st.dataframe(table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                     key="runs_table", column_config={"진행률": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.0f%%")})

rows = event.selection.rows if event and event.selection else []
default = st.session_state.get("selected_run")
ids = [r["run_id"] for r in runs]
chosen = ids[rows[0]] if rows else (default if default in ids else ids[0])
run_dir = config.RUNS_DIR / chosen
status = launcher.refresh_status(run_dir) or {}
params = launcher.load_params(run_dir)

st.subheader(f"선택한 실행: {chosen}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("상태", STATE_LABEL.get(status.get("state"), status.get("state")))
c2.metric("단계", STAGE_LABEL.get(status.get("stage"), status.get("stage") or "-"))
c3.metric("진행률", f"{float(status.get('progress') or 0) * 100:.0f}%")
c4.metric("시드", params.get("seed_id"))
if status.get("error"):
    st.error(status["error"])

b1, b2, b3 = st.columns(3)
if b1.button("같은 설정으로 재실행", key="rerun"):
    try:
        new = launcher.start_run(params)
        st.session_state["active_run"] = new.name
        st.session_state["selected_run"] = new.name
        st.success(f"재실행을 시작했습니다: {new.name} (홈 페이지에서 진행 상황을 볼 수 있습니다)")
    except RuntimeError as exc:
        st.error(str(exc))
if status.get("state") in ("running", "queued") and b2.button("취소", key="cancel"):
    launcher.cancel_run(run_dir)
    st.rerun()
if (run_dir / "scoring.json").exists() and b3.button("순위표 보기", key="goto"):
    st.session_state["selected_run"] = chosen
    st.switch_page("pages/2_Ranking.py")

with st.expander("파라미터 (params.json)"):
    st.json(params)
if (run_dir / "versions.json").exists():
    with st.expander("도구·모델 버전 (versions.json)"):
        st.json(json.loads((run_dir / "versions.json").read_text(encoding="utf-8")))
with st.expander("로그 (마지막 40줄)"):
    st.code(launcher.tail_log(run_dir) or "(비어 있음)", language="text")

if (run_dir / "candidates.csv").exists():
    st.subheader("후보 (구조 QC)")
    df = load_candidates(run_dir)
    if "qc_status" in df.columns:
        f1, f2 = st.columns(2)
        plddt_min = f1.slider("평균 pLDDT 최소", 0.0, 100.0, float(params.get("plddt_min", config.PLDDT_MIN)), key="qc_plddt")
        rmsd_max = f2.slider("시드 대비 RMSD 최대 (Å)", 0.5, 10.0, float(params.get("rmsd_max", config.RMSD_MAX)), step=0.1, key="qc_rmsd")
        df["통과"] = apply_thresholds(df, plddt_min, rmsd_max)
        st.caption(f"임계값을 통과한 후보 {int(df['통과'].sum())}/{len(df)}개 · 구조 예측 실패 {int((df['qc_status'] != 'ok').sum())}개")
        cols = [c for c in ("cand_id", "mutations", "n_mut", "plddt_mean", "plddt_ibs", "rmsd_seed", "esm_llr", "통과", "qc_status") if c in df.columns]
        st.dataframe(df[cols], hide_index=True, width="stretch")
    else:
        st.dataframe(df, hide_index=True, width="stretch")
