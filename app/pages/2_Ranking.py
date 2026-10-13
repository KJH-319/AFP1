"""순위표 + 3D 비교 + 내보내기 (F-11, F-12, F-15).  가중치 슬라이더로 순위가 즉시 바뀐다."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from afp import config  # noqa: E402
from afp.evaluate.scoring import GROUPS, apply_weights, flag_set, load_scoring, normalize_weights  # noqa: E402
from afp.evaluate.structure_qc import apply_thresholds  # noqa: E402
from afp.export.exporter import export_run, zip_export  # noqa: E402
from afp.io.fasta import InputError  # noqa: E402
from afp.io.seeds import load_seed  # noqa: E402
from afp.pipeline import load_candidates  # noqa: E402
from afp.runner import launcher  # noqa: E402
from afp.ui import show_disclaimer, show_validation_banner, viewer_html  # noqa: E402

st.set_page_config(page_title="순위표 · AFP Designer", page_icon="🧊", layout="wide")
st.title("순위표")
show_disclaimer(st)
show_validation_banner(st)

done = [r for r in launcher.list_runs() if r["state"] == "done" and (r["path"] / "candidates.csv").exists()]
if not done:
    st.info("완료된 실행이 없습니다. 홈에서 설계를 실행하세요.")
    st.stop()
ids = [r["run_id"] for r in done]
default = st.session_state.get("selected_run")
run_id = st.selectbox("실행 선택", ids, index=ids.index(default) if default in ids else 0, key="rank_run")
run_dir = config.RUNS_DIR / run_id
params = launcher.load_params(run_dir)
seed = load_seed(params["seed_id"], allow_unverified=bool(params.get("allow_unverified", False)))
df = load_candidates(run_dir)
scoring = load_scoring(run_dir)

if scoring is None or "g_ibs" not in df.columns:
    st.warning("이 실행에는 평가(IBS 지표·점수)가 없습니다. `python -m afp.cli evaluate --run " + run_id + "` 로 추가할 수 있습니다.")
    st.dataframe(df, hide_index=True, width="stretch")
    st.stop()

# ------------------------------------------------------------------ 사이드바: 가중치와 필터
with st.sidebar:
    st.header("점수 가중치")
    st.caption("값을 바꾸면 순위가 즉시 다시 계산됩니다 (합은 자동으로 1로 맞춤).")
    base = scoring["weights"]
    labels = {"structure": "구조 신뢰도", "ibs": "IBS 품질", "afp": "AFP 유사도", "dev": "개발성"}
    weights = {g: st.slider(labels[g], 0.0, 1.0, float(round(base[g], 2)), step=0.05, key=f"w_{g}") for g in GROUPS}
    st.header("필터")
    plddt_min = st.slider("평균 pLDDT 최소", 0.0, 100.0, float(params.get("plddt_min", config.PLDDT_MIN)), key="f_plddt")
    rmsd_max = st.slider("시드 대비 RMSD 최대 (Å)", 0.5, 10.0, float(params.get("rmsd_max", config.RMSD_MAX)), step=0.1, key="f_rmsd")
    hide_dup = st.checkbox("거의 같은 서열(near_duplicate) 숨김", value=True, key="f_dup")
    hide_dev = st.checkbox("개발성 플래그가 있는 후보 숨김", value=False, key="f_dev")
    top_n = st.number_input("표시할 최대 후보 수", 1, 1000, 50, key="f_top")

if sum(weights.values()) <= 0:
    st.error("가중치가 모두 0입니다. 하나 이상 올려 주세요.")
    st.stop()
ranked = apply_weights(df, weights, plddt_min)
mask = apply_thresholds(ranked, plddt_min, rmsd_max)
if hide_dup:
    mask &= ~ranked["flags"].apply(lambda f: "near_duplicate" in flag_set(f))
if hide_dev:
    mask &= ~ranked["flags"].apply(lambda f: bool(flag_set(f) & {"n_glyc", "odd_cys", "hydrophobic_patch"}))
view = ranked[mask].head(int(top_n)).reset_index(drop=True)
view.insert(0, "표시 순위", range(1, len(view) + 1))

st.caption(f"시드: **{seed.name}** · 후보 {len(df)}개 중 필터 통과 {int(mask.sum())}개 · 가중치(정규화): "
           + ", ".join(f"{labels[g]} {v:.2f}" for g, v in normalize_weights(weights).items()))
cols = ["표시 순위", "cand_id", "mutations", "score", "g_structure", "g_ibs", "g_afp", "g_dev", "plddt_mean", "rmsd_seed",
        "ibs_planarity", "ibs_area", "ibs_lattice_dev", "esm_llr", "net_charge", "flags"]
event = st.dataframe(
    view[[c for c in cols if c in view.columns]], hide_index=True, width="stretch",
    on_select="rerun", selection_mode="multi-row", key="rank_table",
    column_config={
        "score": st.column_config.ProgressColumn("점수", min_value=0.0, max_value=1.2, format="%.3f"),
        "g_structure": st.column_config.NumberColumn("구조", format="%.2f"),
        "g_ibs": st.column_config.NumberColumn("IBS", format="%.2f"),
        "g_afp": st.column_config.NumberColumn("AFP", format="%.2f"),
        "g_dev": st.column_config.NumberColumn("개발성", format="%.2f"),
        "plddt_mean": st.column_config.NumberColumn("pLDDT", format="%.1f"),
        "rmsd_seed": st.column_config.NumberColumn("RMSD(Å)", format="%.2f"),
        "ibs_planarity": st.column_config.NumberColumn("평면성(Å)", format="%.2f"),
        "ibs_area": st.column_config.NumberColumn("IBS 면적", format="%.0f"),
        "ibs_lattice_dev": st.column_config.NumberColumn("격자편차(Å)", format="%.2f"),
        "esm_llr": st.column_config.NumberColumn("ESM 로그비", format="%.2f"),
        "net_charge": st.column_config.NumberColumn("순전하", format="%.1f"),
    },
)
picked = list(event.selection.rows) if event and event.selection else []
picked_ids = [view.loc[i, "cand_id"] for i in picked]
st.caption("표에서 행을 선택하면 아래 3D 비교와 내보내기 대상에 반영됩니다.")

with st.expander("점수 정의와 기준값 (scoring.json)"):
    st.json(scoring)

# ------------------------------------------------------------------ 3D 비교
st.subheader("3D 비교")
if not picked_ids:
    st.info("표에서 후보를 1~4개 선택하세요. 시드(회색)와 겹쳐 보여주고 IBS 잔기를 스틱으로 강조합니다.")
else:
    shown = picked_ids[:4]
    if len(picked_ids) > 4:
        st.caption("3D에는 선택한 후보 중 처음 4개만 표시합니다.")
    models = []
    for cid in shown:
        row = view[view["cand_id"] == cid].iloc[0]
        if row["structure_path"]:
            models.append((cid, (run_dir / row["structure_path"]).read_text(encoding="utf-8")))
    legend = " · ".join(f"<span style='color:{config_color}'>■</span> {cid}" for (cid, _), config_color
                        in zip(models, ["#1f77b4", "#d62728", "#2ca02c", "#9467bd"]))
    st.markdown(f"회색: 시드 실험 구조 · {legend}", unsafe_allow_html=True)
    components.html(viewer_html(seed, models), height=540)

# ------------------------------------------------------------------ 내보내기
st.subheader("내보내기")
export_name = st.text_input("내보내기 이름", value=f"{run_id}-top", key="export_name")
n_sel = len(picked_ids) if picked_ids else min(10, len(view))
st.caption(f"{'선택한 ' + str(len(picked_ids)) + '개 후보' if picked_ids else '현재 표의 상위 ' + str(n_sel) + '개'}를 내보냅니다 "
           "(시드 원본 서열이 대조군으로 FASTA 맨 앞에 들어갑니다).")
if st.button("내보내기", key="export_btn"):
    ids_to_export = picked_ids or list(view["cand_id"].head(n_sel))
    try:
        out = export_run(run_dir, export_name, cand_ids=ids_to_export, overwrite=True)
        st.session_state["last_export"] = str(out)
        st.success(f"내보냈습니다: {out}")
    except InputError as exc:
        st.error(str(exc))
last = st.session_state.get("last_export")
if last and Path(last).exists():
    zpath = zip_export(Path(last))
    st.download_button("ZIP 다운로드", data=Path(zpath).read_bytes(), file_name=Path(zpath).name, mime="application/zip", key="dl_zip")
