"""Split digest assert (reuse apigraph loader read-only)."""

from __future__ import annotations

from abrg.apigraph.split import SplitBundle, load_run3_split
from abrg.transitions import EXPECTED_SPLIT_DIGEST_PREFIX


def load_split_or_stop() -> SplitBundle:
    bundle = load_run3_split()
    dig = bundle.sha_list_digest
    if not dig.startswith(EXPECTED_SPLIT_DIGEST_PREFIX):
        raise SystemExit(
            f"STOP: split digest {dig[:16]}… != prefix {EXPECTED_SPLIT_DIGEST_PREFIX}…"
        )
    print(
        f"[transitions] split OK {dig[:12]}… "
        f"{len(bundle.train)}/{len(bundle.test_benign)}/{len(bundle.test_malware)}",
        flush=True,
    )
    return bundle
