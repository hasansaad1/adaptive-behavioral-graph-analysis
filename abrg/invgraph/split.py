"""Assert Run3 split digest matches the pinned prefix."""

from __future__ import annotations

from abrg.apigraph.split import SplitBundle, load_run3_split
from abrg.invgraph import EXPECTED_SPLIT_DIGEST_PREFIX


def load_split_or_stop() -> SplitBundle:
    bundle = load_run3_split()
    dig = bundle.sha_list_digest
    if not dig.startswith(EXPECTED_SPLIT_DIGEST_PREFIX):
        raise SystemExit(
            f"STOP: split SHA digest {dig[:16]}… does not match "
            f"expected prefix {EXPECTED_SPLIT_DIGEST_PREFIX}…"
        )
    print(
        f"[invgraph] split digest OK {dig[:12]}… "
        f"train={len(bundle.train)} test_b={len(bundle.test_benign)} "
        f"test_m={len(bundle.test_malware)}",
        flush=True,
    )
    return bundle
