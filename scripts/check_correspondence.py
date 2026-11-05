"""Actual Vultr raster observations on a genuine retained public research capture."""

import json
import time
from pathlib import Path
from uuid import uuid4

from services.api.settings import AppSettings
from services.artifacts.packet import prepare
from services.artifacts.store import ArtifactStore
from services.common.source_policy import SourceProfile
from services.domain.contracts import RequestItem
from services.domain.correspondence import blockers
from services.runner.correspondence import correspond
from services.runner.vultr import VultrClient


def main():
    folder = Path("var/correspondence-diagnostic")
    folder.mkdir(mode=0o700, exist_ok=True)
    raw = Path("var/supplier-extraction/ubiquiti.capture").read_bytes()
    profile = SourceProfile(
        id="ubiquiti_u6plus_research", version=1, origin="https://store.ui.com",
        offer_paths=["/us/en/products/u6-plus"], main_selector="main",
        asset_origins=["https://assets.ecomm.ui.com", "https://cdn.ecomm.ui.com"],
        expires_at="2026-11-07T00:00:00Z",
    )
    with ArtifactStore(folder / "sanitized") as store:
        packet = prepare(raw, profile, profile.origin + profile.offer_paths[0], store)
    settings = AppSettings(model_id="qwen3.8-flash-next",
                           inference_key_file=Path("private/vultr-inference-key"))
    result, usage = correspond(
        VultrClient(settings, output_token_limit=4096), packet, uuid4(),
        [RequestItem(key="u6_plus", specification="Ubiquiti Access Point U6 Plus",
                     public_specification="Ubiquiti Access Point U6 Plus", required_units=1)],
        deadline=time.monotonic()+45,
        on_invalid=lambda value: (folder/"invalid.json").write_text(json.dumps(value)),
    )
    (folder/"result.json").write_text(json.dumps({"result":result.model_dump(mode="json"),
                                               "usage":usage},indent=2)+"\n")
    assert "IMAGE_CORRESPONDENCE_UNRESOLVED" in blockers(result)
    print(json.dumps({"status":"passed", "actual_calls":usage["calls"],
                      "observations":[o.status for o in result.observations],
                      "scope":"retained_public_source_correspondence_only",
                      "supplier_product_images":"unsupported", "buyer_acceptance":"unverified"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status":"failed","code":type(error).__name__}))
        raise SystemExit(1) from None
