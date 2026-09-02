# Campaign: exp_epochs

## e600_weighted — 2026-08-04 (canonical, seeded)
- Axis: GAE training epochs 300 → 600
- ratio: **1.250** vs baseline 1.20 (Δ +0.05); train_med 0.5606; test_med 0.7008
- Skeptic: prior **improve** revoked — first result non-reproducible (missing `random.seed`)
- Reproduce: **ok** (`validate_reproduce --mode cli`, exact match)
- Next: treat epochs=600 as neutral; do not cite 0.985

## e600_weighted — 2026-08-04 (withdrawn)
- Axis: GAE training epochs 300 → 600
- ratio: 0.9850 vs 1.20 (Δ −0.2150) — **withdrawn**
- Skeptic: improve (invalidated by failed reproduce before seed fix)
- Next: superseded by seeded re-run above
