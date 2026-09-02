# D-3: Referencing versus localisation (2×2 factorial)

Generated: 2026-08-22 (scoring pass only; runner `abrg/devread/run_d3_hygiene.py`)

## Spine (asserted)

| Pin | Value |
|-----|-------|
| Split digest prefix | `6129eb13d6a4` |
| Train-benign | 562 |
| Test-benign | 141 |
| Test-malware | 1700 |
| Mapped-event floor | 0.702500 |
| Malware | scored only, never fitted |

## Reference ladder (catalogue — not all are 2×2 cells)

| Quantity | AUC_floor | Direction | Artifact / note |
|----------|----------:|-----------|-----------------|
| raw ipc share (univariate) | 0.575000 | benign-higher | §A.6.7 catalogue |
| D0 scalar reconstruction | 0.637900 | inverted benign-higher | GAE recon error |
| D0 centred train-benign (cell C) | 0.761669 | malware-higher | `trained__D0__…centroid…json` |
| D1 centroid (cell D) | 0.800426 | malware-higher | `trained__D1__…centroid…json` |
| D3 supervised (diagnostic ceiling) | 0.962400 | — | not in 2×2 |
| RAW input centroid (cell B) | 0.776892 | malware-higher | `raw__RAW_full__…centroid…json` |
| RAW HGB supervised (diagnostic ceiling) | 0.974600 | — | not in 2×2 |

---

## 2×2 design

**Axis A — representation:** RAW = flattened input tensor `X`; DEV = deviation profile vs train-benign reference.  
**Axis B — readout:** SCALAR = one number before scoring; PER-NODE = vector → L2 centroid distance.

| Cell | Repr | Readout | AUC | AUC_floor | Direction | CI95 floor | Clears 0.7025? | Instantiation |
|------|------|---------|----:|----------:|-----------|------------|----------------|---------------|
| **A** | RAW | SCALAR | 0.792674 | 0.792674 | malware-higher | [0.744243, 0.839313] | yes | **No exact persisted artifact.** Minimal: \(s_i=\|X^{\mathrm{raw}}_i\|_2\) (704-d); score \(|\,s_i - \mathrm{mean}_{\mathrm{train\text{-}benign}}(s)\,|\). |
| **B** | RAW | PER-NODE | 0.776892 | 0.776892 | malware-higher | [0.725979, 0.825617] | yes | `abrg/output/androct_2017/ocdev/controls/raw_tensor/raw__RAW_full__none__centroid_euclidean__splitA__foldNA.json` |
| **C** | DEV | SCALAR | 0.761669 | 0.761669 | malware-higher | [0.716735, 0.806956] | yes | D0 (1-d GAE recon); centroid = \(\|D0 - \mu_{\mathrm{train}}\|\). `…/splitA_trained/trained__D0__none__centroid_euclidean__splitA__foldNA.json` |
| **D** | DEV | PER-NODE | 0.800426 | 0.800426 | malware-higher | [0.752788, 0.847177] | yes | D1 (22-d); L2 centroid. `…/splitA_trained/trained__D1__none__centroid_euclidean__splitA__foldNA.json` |

CSV: `results/D3_factorial_2x2.csv`

---

## Margins (floor AUC differences)

| Margin | Δ (floor) | Interpretation |
|--------|----------:|----------------|
| Referencing @ SCALAR readout (C − A) | **−0.031005** | Deviation **hurts** vs RAW L2-norm scalar |
| Referencing @ PER-NODE readout (D − B) | **+0.023534** | Small referencing gain at vector readout |
| Readout on RAW (B − A) | −0.015782 | Per-node readout slightly worse than L2 scalar on RAW |
| Readout on DEV (D − C) | **+0.038757** | Per-node readout helps on DEV representation |
| Interaction (D−B) − (C−A) | **+0.054539** | **Non-additive:** axes interact |

### Paired tests (margins with |Δ| > 0.02; DeLong + bootstrap B=2000, same apps)

| Margin | Δ | DeLong z | DeLong p | Bootstrap 95% CI (Δ_floor) | Spearman ρ | Distinguishable? |
|--------|---|---------|---------|---------------------------|------------|------------------|
| Referencing @ SCALAR | −0.031005 | −1.598897 | 0.109844 | [−0.069095, +0.005466] | 0.528792 | **no** |
| Referencing @ PER-NODE | +0.023534 | +1.612976 | 0.106750 | [−0.004309, +0.053141] | 0.838775 | **no** (also inside D1 nested CI [0.757, 0.815]) |
| Readout on DEV | +0.038757 | +2.344133 | 0.019071 | [+0.007076, +0.071715] | 0.626604 | **yes** |
| Readout on RAW | −0.015782 | — | — | not tested (|Δ|≤0.02) | — | — |
| Interaction | +0.054539 | — | — | derived margin | — | — |

**Which axis carries the climb?** At the factorial level, **readout on the DEV representation** is the only distinguishable margin (+0.039). Referencing at per-node is +0.024 but **not** statistically separable from zero. Referencing at scalar is **negative** (−0.031, not distinguishable). The **interaction (+0.055)** is material: referencing only helps (or hurts less) when readout is per-node; collapsing to scalar first inverts the referencing sign.

This 2×2 does **not** span the full Table A.13 ladder (0.575 ipc → 0.9624 D3 supervised); cells A–D sit in the 0.76–0.80 band except cell A’s L2-norm scalar (0.793).

---

## Per-coordinate referencing (22 rows; 4 N/A)

For each PRODUCIBLE category: univariate RAW (`act_v_frac` node feature) vs univariate DEV (D1 coordinate), benign-only reference, same readout (|value − μ_train|).

**Summary (18 PRODUCIBLE):**

- Positive Δ (dev_floor − raw_floor): **13 / 18**
- Direction reversals: **10 / 18** — not scoped to `ipc_intents` alone

**Sharpest single coordinate (`ipc_intents`):**

| | RAW act_v_frac | DEV D1 coord |
|--|-------------|-------------|
| AUC_floor | 0.562503 (catalogue ipc share: 0.575000) | 0.793191 (catalogue: 0.793000) |
| Direction | benign-higher | malware-higher |
| Δ_floor | +0.230688 | direction **flipped** |

Full table sorted by Δ_floor: `results/D3_per_coordinate.csv`

Non-producible (N/A): `sms`, `telephony`, `clipboard`, `dynamic_code_loading`.

---

## Controls

### 1. Floor vs 0.7025

All four cells clear the mapped-event floor. Shuffled labels on cell D: AUC_floor **0.504937** (noise; below ~0.53).

### 2. Volume covariates (Spearman ρ, test apps, six decimals)

| Covariate | Cell B | Cell C | Cell D |
|-----------|-------:|-------:|-------:|
| mapped_event_count | −0.122785 | +0.167034 | −0.167944 |
| total_event_count | +0.160282 | +0.574255 | +0.278942 |
| edge_count | +0.062852 | +0.410267 | +0.103886 |
| graph_density | +0.062852 | +0.410267 | +0.103886 |
| distinct_active_categories | +0.043611 | +0.373177 | +0.085446 |
| active_nodes | +0.043950 | +0.373584 | +0.085546 |
| static_feature_norm | +0.242634 | +0.381661 | +0.330147 |
| **max \|ρ\| Table A.4** | **0.160282** | **0.574255** | **0.278942** |

D1 reference: max Table A.4 |ρ| = 0.278942; static_feature_norm = 0.330147 — reproduced.

### 3. Shuffled labels (cell D)

AUC_floor = 0.504937; direction = benign-higher; does not clear floor.

---

## Honest bottom line

Arguments **against** a clean “referencing bought the climb” story are as prominent as those for it:

1. **Referencing at scalar readout is negative** (−0.031) — deviation vs train-benign reference is worse than a raw L2-norm summary when readout is collapsed first.
2. **Referencing at per-node is +0.024 but indistinguishable** from zero under paired DeLong/bootstrap; it lies inside D1’s known nested interval.
3. **Only readout-on-DEV (+0.039) is distinguishable** — localisation (per-node centroid on deviation vectors) drives the factorial win, not referencing alone.
4. **Large interaction (+0.055)** — axes are not additive; referencing and readout must be discussed jointly.
5. **Per-coordinate:** 10/18 coordinates flip direction under referencing; the §A.6.7 ipc finding generalises broadly, not as a single-coordinate artefact.

The supervised diagnostic ceilings (D3 0.9624, RAW HGB 0.9746) remain outside this benign-only 2×2 and are **not** proposed detectors.
