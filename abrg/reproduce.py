"""Per-run reproduce config + Jupyter notebook helpers for ABRG experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from abrg.reproduce_kinds import (
    DEFAULT_ATOL_MEDIAN,
    DEFAULT_ATOL_RATIO,
    cli_argv_from_config,
    compare_kind_metrics,
    config_for_androct,
    config_for_negative_control,
    config_from_comparison_ratio,
    extract_metrics_from_result,
    primary_arm_metrics,
    result_json_name,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def compare_metrics(
    expected: dict[str, float],
    actual: dict[str, float],
    *,
    atol_median: float = DEFAULT_ATOL_MEDIAN,
    atol_ratio: float = DEFAULT_ATOL_RATIO,
) -> dict[str, Any]:
    """Backward-compatible ratio metric check (legacy notebooks)."""
    return compare_kind_metrics(
        expected,
        actual,
        kind="ratio",
        config={"atol_median": atol_median, "atol_ratio": atol_ratio},
    )


def write_reproduce_config(run_dir: Path, config: dict[str, Any]) -> Path:
    path = run_dir / "reproduce_config.json"
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def _notebook_header(config: dict[str, Any], rel_run: Path) -> str:
    kind = config.get("kind", "ratio")
    pins = config.get("pins") or {}
    if kind == "ratio":
        pin_line = (
            f"**Pins:** dataset={config.get('dataset')} seed={pins.get('seed')} "
            f"window={pins.get('window_sec')}s epochs={pins.get('epochs')} "
            f"edge_weight={pins.get('edge_weight_in_encoder')} "
            f"scorer={config.get('scorer', 'stochastic')}"
        )
    elif kind == "androct_auc":
        pin_line = f"**Profile:** {config.get('profile')} | module={config.get('cli_module')}"
    else:
        pin_line = f"**Kind:** {kind} | module={config.get('cli_module')}"

    return f"""# Reproduce: `{config.get("run_id", rel_run.name)}`

**Axis:** {config.get("axis", "(see RUN.md)")}

{pin_line}

This notebook re-executes the same CLI as the original run into `nb_repro/` under this run dir, then compares frozen metrics to `reproduce_config.json` expected values.

```bash
cd {REPO_ROOT}
.venv/bin/python -m abrg.validate_reproduce --run-dir {rel_run}
# or: jupyter nbconvert --to notebook --execute {rel_run}/reproduce.ipynb
```
"""


def write_reproduce_notebook(run_dir: Path, config: dict[str, Any]) -> Path:
    """Write a Jupyter notebook that re-runs this experiment and checks metrics."""
    run_dir = run_dir.resolve()
    rel_run = (
        run_dir.relative_to(REPO_ROOT) if run_dir.is_relative_to(REPO_ROOT) else run_dir
    )
    md = _notebook_header(config, rel_run)

    code_setup = f"""from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CWD = Path.cwd().resolve()
REPO_ROOT = CWD if (CWD / "abrg").is_dir() else CWD.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from abrg.reproduce_kinds import (
    cli_argv_from_config,
    compare_kind_metrics,
    extract_metrics_from_result,
    result_json_name,
)

RUN_DIR = (REPO_ROOT / {repr(str(rel_run))}).resolve()
CFG = json.loads((RUN_DIR / "reproduce_config.json").read_text(encoding="utf-8"))
KIND = CFG.get("kind", "ratio")
PROFILE = CFG.get("profile", "")
RESULT_NAME = result_json_name(KIND)
EXPECTED_JSON = RUN_DIR / RESULT_NAME
print("RUN_DIR:", RUN_DIR)
print("kind:", KIND)
print("axis:", CFG.get("axis"))
"""

    code_run = """REPRO_DIR = RUN_DIR / "nb_repro"
if REPRO_DIR.exists():
    import shutil
    shutil.rmtree(REPRO_DIR)
REPRO_DIR.mkdir(parents=True)

argv = [sys.executable, *cli_argv_from_config(CFG, REPRO_DIR)]
print("Running:", " ".join(argv))
proc = subprocess.run(argv, cwd=REPO_ROOT)
print("exit_code:", proc.returncode)
assert proc.returncode == 0, "reproduce CLI failed"
"""

    code_check = """actual_data = json.loads((REPRO_DIR / RESULT_NAME).read_text(encoding="utf-8"))
actual = extract_metrics_from_result(actual_data, kind=KIND, profile=PROFILE)
expected = CFG.get("expected")
if expected is None:
    expected = extract_metrics_from_result(
        json.loads(EXPECTED_JSON.read_text(encoding="utf-8")),
        kind=KIND,
        profile=PROFILE,
    )
report = compare_kind_metrics(expected, actual, kind=KIND, config=CFG)
(RUN_DIR / "nb_validate_report.json").write_text(json.dumps(report, indent=2) + "\\n", encoding="utf-8")
print(json.dumps(report, indent=2))
assert report["ok"], "reproduce metrics outside tolerance — see nb_validate_report.json"
print("REPRODUCE OK")
"""

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": md.splitlines(keepends=True)},
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": code_setup.splitlines(keepends=True),
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": code_run.splitlines(keepends=True),
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": code_check.splitlines(keepends=True),
            },
        ],
    }
    path = run_dir / "reproduce.ipynb"
    path.write_text(json.dumps(nb, indent=1) + "\n", encoding="utf-8")
    return path


def config_from_comparison(
    comparison: dict[str, Any],
    *,
    run_id: str,
    axis: str,
    cli_module: str = "abrg.compare_normalization_ab",
    edge_weight: bool | None = None,
) -> dict[str, Any]:
    return config_from_comparison_ratio(
        comparison,
        run_id=run_id,
        axis=axis,
        cli_module=cli_module,
        edge_weight=edge_weight,
    )


def emit_reproduce_artifacts(
    run_dir: Path,
    *,
    axis: str,
    run_id: str | None = None,
    cli_module: str = "abrg.compare_normalization_ab",
) -> dict[str, Path]:
    """Create reproduce_config.json + reproduce.ipynb from an existing comparison.json."""
    run_dir = Path(run_dir)
    comparison = json.loads((run_dir / "comparison.json").read_text(encoding="utf-8"))
    rid = run_id or run_dir.name
    config = config_from_comparison(
        comparison, run_id=rid, axis=axis, cli_module=cli_module
    )
    return {
        "reproduce_config": write_reproduce_config(run_dir, config),
        "reproduce_notebook": write_reproduce_notebook(run_dir, config),
    }


def emit_reproduce_from_config(run_dir: Path, config: dict[str, Any]) -> dict[str, Path]:
    return {
        "reproduce_config": write_reproduce_config(run_dir, config),
        "reproduce_notebook": write_reproduce_notebook(run_dir, config),
    }
