#!/usr/bin/env python3
"""Generate llama3.2 category predictions for desc_seed experiment (Part B)."""
from __future__ import annotations

import json
import re
import statistics
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

from abrg.api_category_map import HOOK_API_TO_CATEGORY
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

ROOT = Path(__file__).resolve().parent
META = ROOT / "metadata"
PRED_DIR = ROOT / "predictions"
PROMPT_PATH = ROOT / "prompt_template.txt"

EXCLUDED = {
    "ai.susi",
    "at.mikenet.serbianlatintocyrillic",
    "br.odb.knights",
    "buet.rafi.dictionary",
    "cat.jordihernandez.cinecat",
    "app.fedilab.nitterizeme",
}
SEEDS = [42, 43, 44, 45, 46]
MODEL = "llama3.2"
TEMPERATURE = 0.0
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


def _category_definitions() -> dict[str, str]:
    by_cat: dict[str, list[str]] = defaultdict(list)
    for api, cat in HOOK_API_TO_CATEGORY.items():
        if cat in GRAPH_CATEGORY_UNIVERSE:
            by_cat[cat].append(api)
    return {cat: ", ".join(by_cat[cat]) for cat in GRAPH_CATEGORY_UNIVERSE}


def _build_prompt_template() -> str:
    defs = _category_definitions()
    lines = [
        "You predict whether an Android app exercises each of 22 behavioural "
        "categories at runtime.",
        "",
        "Categories are the fixed graph-node universe from Chapter A, mapped "
        "by the Frida hook taxonomy (hook_apis.js v3 / abrg.api_category_map). "
        "Each line lists the hooked API labels for that category:",
        "",
    ]
    for cat in GRAPH_CATEGORY_UNIVERSE:
        lines.append(f"- {cat}: {defs[cat]}")
    lines.extend(
        [
            "",
            "App metadata:",
            "Name: {{name}}",
            "Summary: {{summary}}",
            "Description: {{description}}",
            "",
            "Output strict JSON only: one object with exactly these 22 keys, "
            "each a probability in [0,1] that this app exercises that category "
            "at runtime. Use double-quoted keys. No markdown, no prose, no "
            "reasoning. Keys:",
            ", ".join(GRAPH_CATEGORY_UNIVERSE),
        ]
    )
    return "\n".join(lines) + "\n"


def _fill_prompt(template: str, record: dict) -> str:
    return (
        template.replace("{{name}}", record.get("name") or "")
        .replace("{{summary}}", record.get("summary") or "")
        .replace("{{description}}", record.get("description") or "")
    )


def _json_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            c: {"type": "number", "minimum": 0, "maximum": 1} for c in GRAPH_CATEGORY_UNIVERSE
        },
        "required": list(GRAPH_CATEGORY_UNIVERSE),
        "additionalProperties": False,
    }


def _ollama_generate(prompt: str, seed: int, temperature: float = TEMPERATURE) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": _json_schema(),
        "options": {"temperature": temperature, "seed": seed, "num_predict": 512},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.load(resp)
    return str(body.get("response", ""))


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError("top-level JSON is not an object")
    out: dict[str, float] = {}
    for cat in GRAPH_CATEGORY_UNIVERSE:
        if cat not in obj:
            raise ValueError(f"missing key {cat}")
        val = float(obj[cat])
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"{cat}={val} outside [0,1]")
        out[cat] = val
    extra = set(obj) - set(GRAPH_CATEGORY_UNIVERSE)
    if extra:
        raise ValueError(f"unexpected keys: {sorted(extra)}")
    return out


def _parse_prediction(text: str) -> dict[str, float]:
    try:
        return _extract_json(text)
    except (json.JSONDecodeError, ValueError, TypeError):
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            raise
        return _extract_json(m.group(0))


def _load_apps() -> list[dict]:
    data = json.loads((META / "fdroid_59.json").read_text(encoding="utf-8"))
    apps = []
    for rec in data["records"]:
        if rec is None:
            continue
        if rec["app_id"] in EXCLUDED:
            continue
        if not rec.get("description") or rec.get("description_chars", 0) == 0:
            continue
        apps.append(rec)
    apps.sort(key=lambda r: r["app_id"])
    return apps


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return float("nan")
    mx = statistics.mean(x)
    my = statistics.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    denx = sum((a - mx) ** 2 for a in x) ** 0.5
    deny = sum((b - my) ** 2 for b in y) ** 0.5
    if denx == 0 or deny == 0:
        return float("nan")
    return num / (denx * deny)


def run_seed(
    seed: int,
    template: str,
    apps: list[dict],
    *,
    temperature: float = TEMPERATURE,
) -> dict:
    predictions: dict[str, dict[str, float]] = {}
    failures: list[dict] = []
    for i, rec in enumerate(apps, 1):
        app_id = rec["app_id"]
        prompt = _fill_prompt(template, rec)
        ok = False
        last_err = ""
        raw = ""
        for attempt in range(2):
            try:
                raw = _ollama_generate(prompt, seed, temperature=temperature)
                predictions[app_id] = _parse_prediction(raw)
                ok = True
                break
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
        if not ok:
            failures.append({"app_id": app_id, "error": last_err, "raw": raw[:2000]})
        print(
            f"  seed={seed} temp={temperature} [{i}/{len(apps)}] {app_id} {'OK' if ok else 'FAIL'}",
            flush=True,
        )
    return {
        "seed": seed,
        "model": MODEL,
        "temperature": temperature,
        "n_apps": len(apps),
        "n_success": len(predictions),
        "n_failed": len(failures),
        "parse_success_rate": len(predictions) / len(apps) if apps else 0.0,
        "failures": failures,
        "predictions": predictions,
    }


def summarize(seeds_payload: list[dict], apps: list[dict]) -> dict:
    app_ids = [a["app_id"] for a in apps]
    cats = list(GRAPH_CATEGORY_UNIVERSE)
    by_seed = [p["predictions"] for p in seeds_payload]
    common_apps = set(by_seed[0])
    for preds in by_seed[1:]:
        common_apps &= set(preds)
    common_apps = sorted(common_apps)
    stds: list[float] = []
    for app in common_apps:
        for cat in cats:
            vals = [by_seed[s][app][cat] for s in range(len(by_seed))]
            stds.append(statistics.pstdev(vals) if len(vals) > 1 else 0.0)
    mean_std = statistics.mean(stds) if stds else float("nan")

    corrs: list[float] = []
    flat = []
    for s in range(len(by_seed)):
        flat.append([by_seed[s][app][cat] for app in common_apps for cat in cats])
    for i in range(len(by_seed)):
        for j in range(i + 1, len(by_seed)):
            corrs.append(_pearson(flat[i], flat[j]))
    mean_pairwise_corr = statistics.mean(corrs) if corrs else float("nan")

    cat_means = {}
    for cat in cats:
        vals = [by_seed[s][app][cat] for s in range(len(by_seed)) for app in common_apps]
        cat_means[cat] = statistics.mean(vals) if vals else float("nan")

    return {
        "n_apps_common_across_seeds": len(common_apps),
        "parse_success_rate_per_seed": {
            str(p["seed"]): p["parse_success_rate"] for p in seeds_payload
        },
        "mean_per_app_per_category_std": mean_std,
        "mean_pairwise_seed_correlation": mean_pairwise_corr,
        "pairwise_seed_correlations": corrs,
        "mean_predicted_probability_per_category": cat_means,
        "overall_mean_predicted_probability": statistics.mean(
            list(cat_means.values())
        )
        if cat_means
        else float("nan"),
    }


def main() -> None:
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    template = _build_prompt_template()
    PROMPT_PATH.write_text(template, encoding="utf-8")
    apps = _load_apps()
    if len(apps) != 53:
        raise SystemExit(f"expected 53 apps, got {len(apps)}")

    seeds_payload = []
    for seed in SEEDS:
        print(f"[desc_seed] seed {seed} …", flush=True)
        payload = run_seed(seed, template, apps)
        out = PRED_DIR / f"seed_{seed}.json"
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        seeds_payload.append(payload)

    summary = summarize(seeds_payload, apps)
    (ROOT / "prediction_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
