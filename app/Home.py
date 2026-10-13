"""설계 실행 페이지 (F-1, F-2, F-3, F-5, F-13).  streamlit run app/Home.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from afp import config  # noqa: E402
from afp.io.fasta import InputError, parse_fasta  # noqa: E402
from afp.io.seeds import create_seed, load_all_seeds, parse_residue_spec  # noqa: E402
from afp.runner import launcher  # noqa: E402
from afp.runner.status import read_status  # noqa: E402
from afp.ui import STAGE_LABEL, STATE_LABEL, seed_label, show_disclaimer, show_validation_banner  # noqa: E402

st.set_page_config(page_title="AFP Designer", page_icon="🧊", layout="wide")
st.title("AFP Designer")
st.caption("시드 부동 단백질(AFP)에서 후보를 설계하고 평가해 실험할 서열을 고르는 연구실 내부용 도구")
show_disclaimer(st)
show_validation_banner(st)


@st.fragment(run_every=2)
def live_status(run_id: str) -> None:
    run_dir = config.RUNS_DIR / run_id
    status = launcher.refresh_status(run_dir) or {}
    state = status.get("state", "?")
    st.markdown(f"**실행 `{run_id}`** · 상태: **{STATE_LABEL.get(state, state)}**"
                + (f" · 단계: {STAGE_LABEL.get(status.get('stage'), status.get('stage'))}" if status.get("stage") else ""))
    st.progress(min(max(float(status.get("progress") or 0.0), 0.0), 1.0), text=status.get("message") or "")
    if status.get("error"):
        st.error(status["error"])
    if state in ("running", "queued") and st.button("취소", key=f"cancel_{run_id}"):
        launcher.cancel_run(run_dir)
        st.rerun()
    with st.expander("로그 (마지막 40줄)"):
        st.code(launcher.tail_log(run_dir) or "(비어 있음)", language="text")
    if state == "done":
        st.success("완료되었습니다.")
        if st.button("순위표 보기", key=f"goto_{run_id}"):
            st.session_state["selected_run"] = run_id
            st.switch_page("pages/2_Ranking.py")


# ------------------------------------------------------------------ 시드 선택·등록
seeds = load_all_seeds(allow_unverified=False)
if not seeds:
    st.error("사용할 수 있는 시드가 없습니다. data/seeds를 확인하세요.")
    st.stop()
seed_by_id = {s.id: s for s in seeds}

left, right = st.columns([3, 2])
with left:
    st.subheader("1. 시드 선택")
    seed_ids = list(seed_by_id)
    default_index = seed_ids.index(config.DEFAULT_PARAMS["seed_id"]) if config.DEFAULT_PARAMS["seed_id"] in seed_ids else 0
    seed_id = st.selectbox("시드 AFP", seed_ids, index=default_index, format_func=lambda i: seed_label(seed_by_id[i]), key="seed_id")
    seed = seed_by_id[seed_id]
    st.caption(f"IBS 잔기(문헌 번호): {', '.join(map(str, seed.ibs_residues))} · 구조: {seed.pdb_id or '업로드'} ({seed.structure_source})")
    if seed.ibs_evidence_level != "literature":
        st.warning(f"이 시드의 IBS 근거 수준은 '{seed.ibs_evidence_level}'입니다. 잔기 목록이 불완전할 수 있습니다. "
                   + "근거: " + " / ".join(seed.ibs_evidence[:2]))
    with st.expander("새 시드 등록 (PDB 또는 FASTA 업로드)"):
        with st.form("new_seed"):
            c1, c2 = st.columns(2)
            new_id = c1.text_input("시드 ID (영문·숫자·_·-)", key="new_seed_id")
            new_name = c2.text_input("이름", key="new_seed_name")
            up = st.file_uploader("PDB 또는 FASTA 파일", type=["pdb", "ent", "fasta", "fa", "txt"], key="new_seed_file")
            chain = st.text_input("PDB 체인 (비우면 첫 체인)", key="new_seed_chain")
            ibs_text = st.text_input("IBS 잔기 번호 (예: 9, 14, 15-18)", key="new_seed_ibs")
            go = st.form_submit_button("등록")
        if go:
            try:
                if up is None:
                    raise InputError("파일을 올려 주세요.")
                content = up.getvalue().decode("utf-8", errors="replace")
                ibs_numbers = parse_residue_spec(ibs_text)
                if up.name.lower().endswith((".pdb", ".ent")):
                    created = create_seed(new_id, new_name or new_id, ibs_numbers, pdb_text=content, chain=chain.strip() or None)
                else:
                    from afp.models import get_predictor

                    with st.spinner("ESMFold로 구조를 예측하는 중입니다 (CPU에서는 수십 초~수 분)."):
                        predictor = get_predictor({"backend": st.session_state.get("backend", "real"),
                                                   "structure_model": config.STRUCTURE_MODEL, "device": "auto"},
                                                  template_seed=seed)
                        created = create_seed(new_id, new_name or new_id, ibs_numbers,
                                              fasta_sequence=parse_fasta(content)[0][1], predictor=predictor)
                st.success(f"시드 '{created.id}'를 등록했습니다. 페이지를 새로고침하면 목록에 나타납니다.")
            except InputError as exc:
                st.error(str(exc))

with right:
    st.subheader("2. 설계 파라미터")
    n_candidates = st.slider("후보 수", 5, 500, 100, step=5, key="n_candidates")
    max_mut = st.slider("최대 변이 수", 1, 20, 8, key="max_mut")
    near_ibs = st.slider("IBS 근처 보수적 치환 반경 (Å)", 0.0, 10.0, config.NEAR_IBS_ANGSTROM, step=0.5, key="near_ibs")
    temperature = st.slider("온도 (낮을수록 ESM 선호 변이 위주)", 0.2, 3.0, 1.0, step=0.1, key="temperature")
    rng_seed = st.number_input("난수 시드", 0, 10 ** 6, 1, key="rng_seed")
    with st.expander("고급"):
        backend = st.selectbox("모델 백엔드", ["real", "mock"], key="backend",
                               format_func=lambda b: "실제 모델 (ESM-2, ESMFold)" if b == "real" else "데모용 가짜 모델 (빠름, 결과는 의미 없음)")
        device = st.selectbox("장치", ["auto", "cuda", "cpu"], key="device")

st.subheader("3. 실행")
params = {
    "seed_id": seed.id, "n_candidates": int(n_candidates), "max_mutations": int(max_mut), "near_ibs_angstrom": float(near_ibs),
    "temperature": float(temperature), "rng_seed": int(rng_seed), "backend": backend, "device": device,
}
est = "" if backend == "mock" else " (이 PC처럼 ESMFold를 CPU로 돌리면 후보당 10~20초 정도 걸립니다)"
st.caption(f"후보 {n_candidates}개를 설계하고 구조를 예측·평가합니다.{est}")

if st.button("실행", type="primary", key="run_btn"):
    try:
        run_dir = launcher.start_run(params)
        st.session_state["active_run"] = run_dir.name
        st.session_state["selected_run"] = run_dir.name
    except RuntimeError as exc:
        st.error(str(exc))

active = st.session_state.get("active_run")
if active:
    live_status(active)
else:
    running = [r for r in launcher.list_runs() if r["state"] == "running"]
    if running:
        st.info(f"실행 중인 작업이 있습니다: {running[0]['run_id']}")
        if st.button("진행 상황 보기", key="attach"):
            st.session_state["active_run"] = running[0]["run_id"]
            st.rerun()
