"""양성 대조 검증 (M3-1): 알려진 AFP의 IBS가 같은 크기의 무작위 표면 패치와 구분되는가.

판정 기준은 결과를 보기 전에 정해 둔 것이며 임계값을 결과에 맞춰 바꾸지 않는다.

비교 방향의 사전 가정(ice-binding-like): 평면성 값은 낮을수록, 격자 편차는 낮을수록, IBS 면적은 높을수록
얼음 결합면다운 쪽이다. 소수성 비율은 방향을 가정하지 않아 판정에서 제외하고 참고로만 보고한다.

  - 시드별 통과: 방향성 지표 3개 중 2개 이상에서, 시드의 IBS 값이 음성 대조(비-AFP) 단백질 무작위 패치 분포의
    상위 10%(시드가 90% 이상의 대조 패치보다 얼음 결합면다움)에 든다.
  - 합격: 모든 시드 통과. 부분 합격: 시드의 절반 이상 통과. 불합격: 그 미만.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from afp import config
from afp.evaluate import ibs_metrics as ibs
from afp.io.pdb import parse_pdb, residue_sasa
from afp.io.seeds import load_all_seeds, load_controls

# 값이 클수록 "얼음 결합면다움"인 방향: +1, 작을수록: -1, 가정 없음: 0
DIRECTION = {"ibs_planarity": -1, "ibs_lattice_dev": -1, "ibs_area": +1, "ibs_hydrophobic_frac": 0}
TOP_FRACTION = 0.90          # 대조 패치의 90% 이상보다 낫다
MIN_METRICS_PASS = 2
PARTIAL_FRACTION = 0.5


def percentile_better(x: float, controls: np.ndarray, direction: int) -> float:
    """시드 값이 대조 패치보다 '얼음 결합면다운' 비율(0~1). 방향이 0이거나 NaN이면 NaN."""
    controls = controls[~np.isnan(controls)]
    if direction == 0 or math.isnan(x) or len(controls) == 0:
        return float("nan")
    return float(np.mean(controls > x)) if direction < 0 else float(np.mean(controls < x))


def _structure(entry, predictor, cache_dir):
    """실험 구조 또는(예측기가 있으면) 같은 서열의 예측 구조."""
    if predictor is None:
        return entry.residues(), entry.structure_text()
    from afp.evaluate.structure_qc import predict_cached

    pred, _ = predict_cached(predictor, entry.sequence, cache_dir)
    return parse_pdb(pred.pdb_text, "A"), pred.pdb_text


def run_validation(n_patches: int = config.RANDOM_PATCH_COUNT, rng_seed: int = 1, predictor=None, cache_dir=None,
                   seeds=None, controls=None) -> dict:
    seeds = seeds if seeds is not None else load_all_seeds()
    controls = controls if controls is not None else load_controls()
    cache_dir = cache_dir or config.CACHE_DIR
    rng = np.random.default_rng(rng_seed)

    control_structs = []
    for c in controls:
        res, text = _structure(c, predictor, cache_dir)
        control_structs.append((c, res, text, residue_sasa(text)))

    rows, n_pass = [], 0
    for seed in seeds:
        res, text = _structure(seed, predictor, cache_dir)
        sasa = residue_sasa(text)
        k = len(seed.ibs_indices)
        x_seed = ibs.metrics_for_indices(res, seed.sequence, seed.ibs_indices, sasa)
        own = ibs.random_patch_metrics(res, seed.sequence, text, k, n_patches, rng, sasa)
        ctrl = []
        for c, cres, ctext, csasa in control_structs:
            ctrl += ibs.random_patch_metrics(cres, c.sequence, ctext, k, n_patches, rng, csasa)
        metrics = {}
        for name in ibs.METRIC_NAMES:
            own_vals = np.array([m[name] for m in own], dtype=float)
            ctrl_vals = np.array([m[name] for m in ctrl], dtype=float)
            # 사후 탐색용: 사전 가정과 반대 방향으로 봤을 때의 비율 (판정에는 쓰지 않는다)
            reverse = percentile_better(x_seed[name], ctrl_vals, -DIRECTION[name]) if DIRECTION[name] else float("nan")
            metrics[name] = {
                "x_seed": x_seed[name],
                "own_median": float(np.nanmedian(own_vals)),
                "control_median": float(np.nanmedian(ctrl_vals)),
                "better_than_own_patches": percentile_better(x_seed[name], own_vals, DIRECTION[name]),
                "better_than_control_patches": percentile_better(x_seed[name], ctrl_vals, DIRECTION[name]),
                "reverse_better_than_control_patches": reverse,
            }
        hits = [n for n, m in metrics.items() if DIRECTION[n] != 0 and m["better_than_control_patches"] >= TOP_FRACTION]
        exploratory = [n for n, m in metrics.items() if DIRECTION[n] != 0 and max(
            m["better_than_control_patches"], m["reverse_better_than_control_patches"]) >= TOP_FRACTION]
        passed = len(hits) >= MIN_METRICS_PASS
        n_pass += passed
        rows.append({"seed_id": seed.id, "evidence_level": seed.ibs_evidence_level, "ibs_size": k, "metrics": metrics,
                     "hits": hits, "passed": passed, "hits_either_direction": exploratory})

    frac = n_pass / len(rows) if rows else 0.0
    verdict = "합격" if rows and n_pass == len(rows) else "부분 합격" if frac >= PARTIAL_FRACTION else "불합격"
    return {
        "settings": {"n_patches": n_patches, "rng_seed": rng_seed, "structure": "predicted" if predictor else "experimental",
                     "controls": [c.id for c in controls], "top_fraction": TOP_FRACTION,
                     "min_metrics_pass": MIN_METRICS_PASS, "direction": DIRECTION},
        "seeds": rows,
        "summary": {"verdict": verdict, "seeds_passed": n_pass, "seeds_total": len(rows)},
    }


def _fmt(v, digits=3):
    return "-" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{digits}f}"


def write_report(result: dict, path: Path) -> Path:
    s = result["settings"]
    lines = [
        "# 양성 대조 검증 보고서 (M3-1)", "",
        f"**판정: {result['summary']['verdict']}** (시드 {result['summary']['seeds_passed']}/{result['summary']['seeds_total']}개 통과)", "",
        "알려진 AFP 시드의 IBS 지표가 비-AFP 단백질의 같은 크기 무작위 표면 패치와 구분되는지 확인한 예비 검증이다. "
        "시드가 3개뿐이라 통계 검정 대신 순위 분리로 판정했고, 결과를 일반화하기에는 표본이 작다.", "",
        "## 설정", "",
        f"- 구조: {s['structure']} · 무작위 패치 수: 시드당 {s['n_patches']}개(음성 대조 단백질마다) · 난수 시드: {s['rng_seed']}",
        f"- 음성 대조: {', '.join(s['controls'])}",
        "- 판정 기준(결과를 보기 전에 정함): 방향성 지표(평면성↓, 격자 편차↓, IBS 면적↑) 3개 중 "
        f"{s['min_metrics_pass']}개 이상에서 시드 IBS가 대조 패치의 {int(s['top_fraction'] * 100)}% 이상보다 얼음 결합면다움. "
        "모든 시드 통과 = 합격, 절반 이상 = 부분 합격, 그 미만 = 불합격. 소수성 비율은 방향을 가정하지 않아 참고만 한다.", "",
        "## 시드별 결과", "",
        "표의 '대조 패치보다 나음'은 시드 값이 비-AFP 무작위 패치 중 몇 %보다 얼음 결합면다운 쪽인지(방향 가정 기준)이다. "
        "'자기 패치보다 나음'은 같은 시드 단백질의 무작위 표면 패치와의 비교다.", "",
        "| 시드 | 근거 수준 | IBS 크기 | 지표 | 시드 값 | 시드 자기 패치 중앙값 | 대조 패치 중앙값 | 자기 패치보다 나음 | 대조 패치보다 나음 | 통과 지표 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in result["seeds"]:
        for i, (name, m) in enumerate(r["metrics"].items()):
            first = i == 0
            lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                r["seed_id"] if first else "", r["evidence_level"] if first else "", r["ibs_size"] if first else "", name,
                _fmt(m["x_seed"]), _fmt(m["own_median"]), _fmt(m["control_median"]),
                _fmt(m["better_than_own_patches"], 2), _fmt(m["better_than_control_patches"], 2),
                ("통과" if name in r["hits"] else "") if DIRECTION[name] else "참고"))
        lines.append(f"| | | | **시드 판정** | **{'통과' if r['passed'] else '미통과'}** | | | | | {len(r['hits'])}/3 |")
    lines += ["", "## 사후 탐색 (판정에 쓰지 않음)", "",
              "결과를 본 뒤에 한 분석이다. 사전에 가정한 방향이 틀렸는지 보기 위해 지표별로 두 방향 모두에서 시드가 대조 패치의 "
              f"{int(s['top_fraction'] * 100)}% 이상보다 극단적인지 표시한다. 방향을 결과에 맞춰 고르면 과적합이므로, "
              "이 표는 지표 정의를 개선할 가설을 세우는 데만 쓰고 판정과 점수에는 반영하지 않았다.", "",
              "| 시드 | 지표 | 가정한 방향에서 | 반대 방향에서 | 어느 방향이든 극단적 |", "| --- | --- | --- | --- | --- |"]
    for r in result["seeds"]:
        for name, m in r["metrics"].items():
            if not DIRECTION[name]:
                continue
            lines.append("| {} | {} | {} | {} | {} |".format(
                r["seed_id"], name, _fmt(m["better_than_control_patches"], 2), _fmt(m["reverse_better_than_control_patches"], 2),
                "예" if name in r["hits_either_direction"] else ""))
    lines += ["", "## 해석 시 주의", "",
              "- 이 검증은 IBS **지표**가 시드의 IBS와 무작위 패치를 구분하는지만 본다. 설계 후보의 실제 얼음 결합 활성은 검증하지 않는다.",
              "- 근거 수준이 `derived`나 `literature_partial`인 시드는 IBS 잔기 목록 자체가 불완전할 수 있어 결과 해석에 주의한다.",
              "- Type I처럼 IBS 잔기 사이 거리가 격자 쌍 범위(3~10 Å)를 벗어나는 시드는 격자 편차를 계산할 수 없다(NaN).",
              "- 지표 정의를 바꾸면 이 보고서를 다시 만들고, 변경 이유를 docs/dev/M2-ibs-metrics-ranking-ui.md에 남긴다."]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    import json

    path.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
