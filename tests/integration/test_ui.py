"""Streamlit AppTest로 세 페이지의 핵심 동작을 확인한다 (모델은 mock)."""
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from afp import config
from afp.pipeline import execute_run, load_candidates
from afp.runner import launcher

pytestmark = pytest.mark.integration

APP = Path(__file__).resolve().parents[2] / "app"
PARAMS = {"seed_id": "type3_hplc12", "n_candidates": 14, "max_mutations": 4, "backend": "mock", "mcmc_steps": 40,
          "random_patches": 30, "rng_seed": 3}


def _page(name: str) -> AppTest:
    return AppTest.from_file(str(APP / name), default_timeout=90)


def _finished_run():
    run_dir = launcher.create_run(PARAMS)
    assert execute_run(run_dir) == 0
    return run_dir


def _texts(elements):
    return " ".join(str(e.value) for e in elements)


def test_home_page_shows_disclaimer_and_seeds(isolated_dirs):
    at = _page("Home.py").run()
    assert not at.exception
    assert config.DISCLAIMER in _texts(at.warning)
    options = at.selectbox(key="seed_id").options          # 표시용 라벨 목록
    assert len(options) >= 3 and any("Type III" in o for o in options)
    assert at.selectbox(key="seed_id").value in {"type3_hplc12", "tmafp_beetle", "type1_hplc6"}
    assert at.button(key="run_btn") is not None


def test_home_runs_a_mock_design_in_background(isolated_dirs):
    at = _page("Home.py").run()
    at.selectbox(key="backend").set_value("mock")
    at.slider(key="n_candidates").set_value(5)
    at.slider(key="max_mut").set_value(3)
    at.button(key="run_btn").click().run()
    assert not at.exception
    run_id = at.session_state["active_run"]
    t0 = time.time()
    while time.time() - t0 < 90:
        st = launcher.refresh_status(config.RUNS_DIR / run_id)
        if st["state"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert st["state"] == "done", launcher.tail_log(config.RUNS_DIR / run_id)
    assert (config.RUNS_DIR / run_id / "candidates.csv").exists()


def test_runs_page_lists_run_and_filters(isolated_dirs):
    run_dir = _finished_run()
    at = _page("pages/1_Runs.py").run()
    assert not at.exception
    assert run_dir.name in str(at.dataframe[0].value["실행"].tolist())
    at.slider(key="qc_plddt").set_value(99.0).run()
    assert "통과한 후보 0/" in _texts(at.caption)


def test_runs_page_empty_state(isolated_dirs):
    at = _page("pages/1_Runs.py").run()
    assert not at.exception and "아직 실행 기록이 없습니다" in _texts(at.info)


def test_ranking_page_weights_reorder_table_and_disclaimer_is_always_shown(isolated_dirs):
    run_dir = _finished_run()
    at = _page("pages/2_Ranking.py").run()
    assert not at.exception
    assert config.DISCLAIMER in _texts(at.warning)
    first = list(at.dataframe[0].value["cand_id"])
    df = load_candidates(run_dir)
    for g in ("structure", "ibs", "afp", "dev"):
        at.slider(key=f"w_{g}").set_value(0.0)
    at.slider(key="w_structure").set_value(1.0).run()
    by_structure = list(at.dataframe[0].value["cand_id"])
    assert by_structure[0] == df.loc[df["g_structure"].idxmax(), "cand_id"]
    for g in ("structure", "ibs", "afp", "dev"):
        at.slider(key=f"w_{g}").set_value(0.0)
    at.slider(key="w_afp").set_value(1.0).run()
    by_afp = list(at.dataframe[0].value["cand_id"])
    assert by_afp[0] == df.loc[df["g_afp"].idxmax(), "cand_id"]
    assert by_structure != by_afp or first != by_afp
    assert config.DISCLAIMER in _texts(at.warning)


def test_ranking_thresholds_filter_rows(isolated_dirs):
    _finished_run()
    at = _page("pages/2_Ranking.py").run()
    n_all = len(at.dataframe[0].value)
    at.slider(key="f_plddt").set_value(99.0).run()
    assert len(at.dataframe[0].value) < n_all


def test_ranking_export_button_creates_package(isolated_dirs):
    run_dir = _finished_run()
    at = _page("pages/2_Ranking.py").run()
    at.text_input(key="export_name").set_value("ui-export")
    at.button(key="export_btn").click().run()
    assert not at.exception
    out = config.EXPORTS_DIR / "ui-export"
    assert (out / "candidates.fasta").exists() and (out / "README.txt").exists()
    assert config.DISCLAIMER.split("(")[0] in (out / "README.txt").read_text(encoding="utf-8")
    assert run_dir.name in (out / "README.txt").read_text(encoding="utf-8")


def test_scenario_1_end_to_end_through_the_ui(isolated_dirs):
    """시드 선택 -> 설계 실행 -> 순위표(가중치 조정) -> 내보내기를 UI만으로 끝까지."""
    home = _page("Home.py").run()
    home.selectbox(key="backend").set_value("mock")
    home.slider(key="n_candidates").set_value(8)
    home.slider(key="max_mut").set_value(3)
    home.button(key="run_btn").click().run()
    run_id = home.session_state["active_run"]
    t0 = time.time()
    while time.time() - t0 < 90 and launcher.refresh_status(config.RUNS_DIR / run_id)["state"] not in ("done", "failed"):
        time.sleep(0.5)
    assert launcher.refresh_status(config.RUNS_DIR / run_id)["state"] == "done"

    rank = _page("pages/2_Ranking.py")
    rank.session_state["selected_run"] = run_id
    rank.run()
    assert not rank.exception and len(rank.dataframe[0].value) >= 1
    rank.slider(key="w_ibs").set_value(0.9).run()
    assert not rank.exception
    rank.text_input(key="export_name").set_value("scenario1")
    rank.button(key="export_btn").click().run()
    out = config.EXPORTS_DIR / "scenario1"
    assert (out / "candidates.fasta").exists() and (out / "ranking.csv").exists()


def test_ranking_page_without_runs(isolated_dirs):
    at = _page("pages/2_Ranking.py").run()
    assert not at.exception and "완료된 실행이 없습니다" in _texts(at.info)
