"""Worker configuration assertions. No Docker or live network result is mocked."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from services.supervisor.spike import SECCOMP_SHA256, WorkerSettings, cleanup_task

IMAGE = "registry.example.com/latch@sha256:" + "a" * 64


@pytest.mark.parametrize(
    "changes",
    [
        {"image": "registry.example.com/latch:latest"},
        {"image": "--privileged@sha256:" + "a" * 64},
        {"image": "registry.example.com/latch@sha256:short"},
        {"network": "host"},
        {"network": "bridge"},
        {"network": "none"},
        {"network": "--arbitrary"},
        {"proxy": "http://user:secret@172.28.0.2:3128"},
        {"proxy": "http://172.28.0.2:3128/?token=value"},
        {"proxy": "https://172.28.0.2:3128"},
        {"runtime": "runc"},
        {"privileged": True},
        {"memory": "unlimited"},
        {"mount": "/var/run/docker.sock"},
    ],
)
def test_runtime_authority_cannot_be_supplied(changes):
    values = {"image": IMAGE, "network": "latch_egress", "proxy": "http://172.28.0.2:3128"}
    with pytest.raises(ValidationError):
        WorkerSettings(**(values | changes))


def test_cleanup_requires_exact_opaque_operation_id():
    for value in ("", "../other", "other-container", "a" * 31, "a" * 33, "--all"):
        with pytest.raises(ValueError):
            cleanup_task(value)


def test_local_image_content_address_is_immutable_and_registry_free():
    settings = WorkerSettings(
        image="sha256:" + "a" * 64,
        network="latch_egress",
        proxy="http://172.28.0.2:3128",
    )
    assert settings.image.startswith("sha256:")
    for image in ("latch-browser:p0", "sha256:short", "sha256:" + "A" * 64):
        with pytest.raises(ValidationError):
            WorkerSettings(image=image, network="latch_egress", proxy="http://172.28.0.2:3128")


def test_pinned_seccomp_bytes_and_base_image_match_provenance():
    provenance = json.loads(Path("infra/browser/PROVENANCE.json").read_text())
    digest = hashlib.sha256(Path("infra/browser/seccomp.json").read_bytes()).hexdigest()
    assert digest == SECCOMP_SHA256 == provenance["seccomp_sha256"]
    assert provenance["registry_index_digest"] in Path("infra/browser/Dockerfile").read_text()
    evidence = json.loads(Path(provenance["containment_evidence"]).read_text())
    assert provenance["result_image_digest"] == evidence["browser_image"]
    assert provenance["result_image_digest"].startswith("sha256:")
    assert evidence["supplier_acceptance"] == "pending"
