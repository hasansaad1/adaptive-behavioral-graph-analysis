"""Stage 5 — generate executable notebooks that only read saved artifacts."""
from __future__ import annotations

import nbformat as nbf
from pathlib import Path

from lib import CHAPTER_A

NB = CHAPTER_A / "notebooks"

SETUP = """\
from pathlib import Path
import os, json, csv
import pandas as pd
import numpy as np

ROOT = Path.cwd()
if not (ROOT / "chapter_a").is_dir():
    for cand in (Path(".."), Path("../.."), Path("../../..")):
        if (cand.resolve() / "chapter_a").is_dir():
            ROOT = cand.resolve()
            break
os.chdir(ROOT)
MASTER = pd.read_csv(ROOT / "chapter_a" / "MASTER_RESULTS.csv")
ANDROCT = ROOT / "abrg" / "output" / "androct_2017"

def row_eq(mask, artifact_auc):
    sub = MASTER.loc[mask]
    assert len(sub) >= 1, mask
    mval = float(sub.iloc[0]["auc_floor"])
    aval = float(artifact_auc)
    assert round(mval, 6) == round(aval, 6), (mval, aval)
"""


def _nb(cells):
    nb = nbf.v4.new_notebook()
    nb["metadata"]["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nb["cells"] = cells
    return nb


def _md(s):
    return nbf.v4.new_markdown_cell(s)


def _code(s):
    return nbf.v4.new_code_cell(s)


def write_01():
    cells = [
        _md("# 01 Corpus and validation\n\n**Question.** What is the AndroCT 2017 eligible population, and which corpus/validation numbers in MASTER_RESULTS.csv are stored in artifacts?"),
        _code(SETUP),
        _md("Corpus inventory from post-_CALL_RE `inventory_summary.json` (population), with eligible/split from run2 cache."),
        _code(
            """\
inv = json.loads((ROOT / "datasets/androct_2017/inventory/inventory_summary.json").read_text())
meta = json.loads((ANDROCT / "run2" / "corpus_cache" / "meta.json").read_text())
t1 = pd.read_csv(ROOT / "chapter_a" / "tables" / "T1_corpus.csv")
pop = t1[t1.stage == "population"]
print(pop.to_string(index=False))
for lab in ("benign", "malware"):
    c = inv["classes"][lab]
    row = pop[pop["class"] == lab].iloc[0]
    assert int(row.n_effective) == int(c["n_effective"])
    assert round(float(row.mapped_rate), 6) == round(float(c["mapped_event_rate"]), 6)
    assert int(row.categories_firing) == int(c["n_universe_cats_active"])
print("eligible", meta["n_eligible"], meta["eligibility"]["eligible"])
print("split", {k: len(v) for k, v in meta["split"].items()})
"""
        ),
        _md("Mapped-event size floor from `run3/floors.json`."),
        _code(
            """\
fl = json.loads((ANDROCT / "run3" / "floors.json").read_text())
floor = fl["mapped_event_count"]["auc_floor"]
row_eq(
    (MASTER.experiment == "run3") & (MASTER.detector == "mapped_event_count"),
    floor,
)
print("mapped floor", floor)
"""
        ),
        _md("Final cell: MASTER vs artifacts to 6 decimal places."),
        _code(
            """\
assert round(float(MASTER.loc[(MASTER.detector=="mapped_event_count"), "auc_floor"].iloc[0]), 6) == round(floor, 6)
print("ok")
"""
        ),
    ]
    (NB / "01_corpus_and_validation.ipynb").write_text(nbf.writes(_nb(cells)))


def write_02():
    cells = [
        _md("# 02 Method sweep\n\n**Question.** Do the seven families in T3 match MASTER_RESULTS.csv (trained vs untrained, floors)?"),
        _code(SETUP),
        _code(
            """\
print(pd.read_csv(ROOT / "chapter_a" / "tables" / "T3_method_sweep.csv").to_string(index=False))
fam = json.loads((ANDROCT / "ocdev" / "validation" / "check2_randominit" / "check2.json").read_text())["families"]
c8 = json.loads((ANDROCT / "run8" / "comparison.json").read_text())
t = c8["by_encoder"]["trained_run5"]["reps"]["mean"]["scorers"]["centroid_euclidean"]["auc_floor"]
u = c8["by_encoder"]["random_init"]["reps"]["mean"]["scorers"]["centroid_euclidean"]["auc_floor"]
row_eq((MASTER.detector=="gae_embedding_centroid_mean") & (MASTER.method=="trained"), t)
row_eq((MASTER.detector=="gae_embedding_centroid_mean") & (MASTER.method=="untrained"), u)
row_eq((MASTER.detector=="OCGIN_plus") & (MASTER.method=="trained"), fam["OCGIN"]["trained_mean"])
row_eq((MASTER.detector=="s_graph_full") & (MASTER.method=="trained"), fam["GLocalKD"]["trained_mean"])
row_eq((MASTER.detector=="ocgtl_K4") & (MASTER.method=="trained"), fam["OCGTL"]["trained_mean"])
print("ok")
"""
        ),
    ]
    (NB / "02_method_sweep.ipynb").write_text(nbf.writes(_nb(cells)))


def write_03():
    cells = [
        _md("# 03 Supervision ladder\n\n**Question.** What are the rung-1, rung-2 pooled-OOF, and random-group numbers, and how do per-fold raw vs floor differ?"),
        _code(SETUP),
        _code(
            """\
print(pd.read_csv(ROOT / "chapter_a" / "tables" / "T4_supervision_ladder.csv").to_string(index=False))
r1 = json.loads((ANDROCT / "ladder" / "rung1" / "rung1.json").read_text())
r2 = json.loads((ANDROCT / "ladder" / "rung2" / "behavioral_group_holdout.json").read_text())
rg = json.loads((ANDROCT / "ladder" / "control" / "random_group_holdout.json").read_text())
hgb = r1["modes"]["full"]["models"]["hist_gradient_boosting"]["auc"]["auc_floor"]
pooled = r2["pooled_oof_hgb_full"]["auc_floor"]
row_eq((MASTER.experiment=="ladder") & (MASTER.detector=="HGB") & (MASTER.method=="supervised"), hgb)
row_eq(MASTER.detector=="HGB_pooled_oof_raw", pooled)
n_inv = sum(1 for f in r2["folds"] if f["modes"]["full"]["hist_gradient_boosting"]["auc"]["auc"] < 0.5)
print("n_folds raw<0.5", n_inv)
print("random-group mean floor", rg.get("aggregate", {}).get("full", {}))
print("ok")
"""
        ),
    ]
    (NB / "03_supervision_ladder.ipynb").write_text(nbf.writes(_nb(cells)))


def write_04():
    cells = [
        _md("# 04 Message passing\n\n**Question.** How do M1/M2/M3 compare across poolings and splits, and what do the WL ablations store?"),
        _code(SETUP),
        _code(
            """\
print(pd.read_csv(ROOT / "chapter_a" / "tables" / "T5_message_passing.csv").to_string(index=False))
ab = json.loads((ANDROCT / "kernels" / "ablation" / "winner_ablation.json").read_text())
row_eq(MASTER.detector=="WL_edges_removed", ab["edges_removed_auc_floor"])
row_eq(MASTER.detector=="WL_structure_only_features_constant", ab["features_constant_auc_floor"])
sa = json.loads((ANDROCT / "supgnn" / "splitA" / "splitA_results.json").read_text())
floors = [s["auc"]["auc_floor"] for s in sa["T22"]["mean"]["M1_full"]["per_seed"]]
mean = float(np.mean(floors))
row_eq((MASTER.representation=="T22_mean") & (MASTER.method=="M1_full") & (MASTER.split=="splitA_stratified"), mean)
print("ok")
"""
        ),
    ]
    (NB / "04_message_passing.ipynb").write_text(nbf.writes(_nb(cells)))


def write_05():
    cells = [
        _md("# 05 Deviation readout\n\n**Question.** What are D0–D5 one-class and supervised AUCs on both splits, including the raw-input control?"),
        _code(SETUP),
        _code(
            """\
print(pd.read_csv(ROOT / "chapter_a" / "tables" / "T6_deviation_readout.csv").to_string(index=False))
d1 = json.loads((ANDROCT / "ocdev" / "partA_profiles" / "splitA_trained" / "trained__D1__none__centroid_euclidean__splitA__foldNA.json").read_text())
row_eq((MASTER.experiment=="ocdev") & (MASTER.representation=="D1_trained_t22") & (MASTER.detector=="centroid_euclidean") & (MASTER.split=="splitA_GAE"), d1["auc"]["auc_floor"])
raw = json.loads((ANDROCT / "ocdev" / "controls" / "raw_tensor" / "raw__RAW_full__none__centroid_euclidean__splitA__foldNA.json").read_text())
row_eq(MASTER.method=="raw_input_control", raw["auc"]["auc_floor"])
dr = json.loads((ANDROCT / "devread" / "splitA" / "results_trained.json").read_text())
row_eq((MASTER.experiment=="devread") & (MASTER.representation=="D3_trained_t22") & (MASTER.detector=="HGB") & (MASTER.split=="splitA_stratified"), dr["D3"]["HGB"]["per_seed"][0]["auc"]["auc_floor"])
print("ok")
"""
        ),
    ]
    (NB / "05_deviation_readout.ipynb").write_text(nbf.writes(_nb(cells)))


def write_06():
    cells = [
        _md("# 06 Headline validation\n\n**Question.** Which headline numbers in MASTER_RESULTS.csv match the nested-bootstrap, operating-point, volume, and holdout artifacts?"),
        _code(SETUP),
        _code(
            """\
print(MASTER.loc[MASTER.is_headline.astype(str)=="True", ["experiment","detector","auc_floor","ci_low","ci_high","ci_type"]].to_string(index=False))
bias = json.loads((ANDROCT / "ocdev" / "validation" / "check1_bias" / "bias_stats.json").read_text())
d1p = bias["partA_D1_centroid"]["full_sample_point"]
s1m = bias["partB_T1K_S1_norm"]["bootstrap"]["mean"]
row_eq(MASTER.detector=="centroid_euclidean_nested_form", d1p)
row_eq(MASTER.detector=="S1_norm_nested_bootstrap_mean", s1m)
op = json.loads((ANDROCT / "final_validation" / "check2_operating" / "check2.json").read_text())
print(pd.read_csv(ROOT / "chapter_a" / "tables" / "T7_operating_points.csv").head())
c4 = json.loads((ANDROCT / "final_validation" / "check4_benign_holdout" / "check4.json").read_text())
# pooled centroid
pc = c4["centroid_euclidean"]["pooled_oof_raw"]["auc_floor"]
row_eq((MASTER.experiment=="final_validate") & (MASTER.detector=="centroid_euclidean"), pc)
print("ok")
"""
        ),
    ]
    (NB / "06_headline_validation.ipynb").write_text(nbf.writes(_nb(cells)))


def make_notebooks():
    NB.mkdir(parents=True, exist_ok=True)
    write_01()
    write_02()
    write_03()
    write_04()
    write_05()
    write_06()


if __name__ == "__main__":
    make_notebooks()
    print("notebooks written to", NB)
