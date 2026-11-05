"""Policy and actual local storage checks, not live supplier or Vultr acceptance."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from services.common.config import Settings, read_secret
from services.common.preflight import gate_report, require_json_object
from services.common.source_policy import (
    BuyerItem,
    SourceProfile,
    public_https_url,
    require_public_addresses,
)
from services.common.sqlite import assert_runtime, connect
from services.runner.vultr import ProviderFailure, VultrClient


@pytest.mark.parametrize(
    "url",
    [
        "http://vendor.example.com/offer",
        "https://user:password@vendor.example.com/offer",
        "https://vendor.example.com/offer?token=private",
        "https://vendor.example.com/offer?product=1",
        "https://vendor.example.com/offer#code",
        "https://vendor.example.com:444/offer",
        "https://127.0.0.1/offer",
        "https://[::1]/offer",
        "https://[::ffff:127.0.0.1]/offer",
        "https://169.254.169.254/offer",
        "https://2130706433/offer",
        "https://0177.0.0.1/offer",
        "https://0x7f000001/offer",
        "https://localhost/offer",
        "https://vendor.internal/offer",
        "https://vendor.example.com./offer",
        "https://vendor.example.com/../offer",
        "https://vendor.example.com/%2e%2e/offer",
        "https://vendor.example.com/%252e%252e/offer",
        "https://vendor.example.com/%00offer",
        "https://vendor.example.com\\@169.254.169.254/offer",
        "https://vendor.example.com/\nheader",
    ],
)
def test_secret_and_ambiguous_urls_are_denied(url):
    with pytest.raises(ValueError):
        public_https_url(url)


@pytest.mark.parametrize(
    "addresses",
    [
        [],
        ["127.0.0.1"],
        ["10.0.0.1"],
        ["172.16.0.1"],
        ["192.168.1.1"],
        ["169.254.169.254"],
        ["0.0.0.0"],
        ["100.64.0.1"],
        ["::1"],
        ["fe80::1"],
        ["fd00::1"],
        ["::ffff:169.254.169.254"],
        ["8.8.8.8", "10.0.0.1"],
        ["2001:db8::1"],
    ],
)
def test_all_dns_answers_must_be_public(addresses):
    with pytest.raises(ValueError):
        require_public_addresses(addresses)


def test_public_addresses_are_normalized():
    assert require_public_addresses(["8.8.8.8", "2606:4700:4700::1111"]) == (
        "8.8.8.8",
        "2606:4700:4700::1111",
    )


def test_profile_requires_exact_origin_path_and_active_version():
    now = datetime.now(UTC)
    profile = SourceProfile(
        id="policy_unit_check",
        version=1,
        origin="https://vendor.example.com",
        offer_paths=["/offer"],
        main_selector="main",
        expires_at=now + timedelta(hours=1),
    )
    assert profile.admit("https://vendor.example.com/offer", now).endswith("/offer")
    for url in ("https://other.example.com/offer", "https://vendor.example.com/offer/extra"):
        with pytest.raises(ValueError):
            profile.admit(url, now)
    with pytest.raises(ValueError):
        profile.admit("https://vendor.example.com/offer", now + timedelta(hours=2))


@pytest.mark.parametrize("quantity", [True, False, 0, -1, 10001, 1.5, "2"])
def test_quantity_requires_bounded_integer(quantity):
    with pytest.raises(ValidationError):
        BuyerItem(public_specification="Policy unit assertion", required_units=quantity)


def test_missing_and_zero_are_distinct():
    with pytest.raises(ValidationError):
        BuyerItem(public_specification="Policy unit assertion")
    with pytest.raises(ValidationError):
        BuyerItem(public_specification="Policy unit assertion", required_units=0)


def test_configuration_rejects_other_providers_and_unknown_fields():
    with pytest.raises(ValidationError):
        Settings(inference_base_url="https://other-provider.example.com/v1")
    with pytest.raises(ValidationError):
        Settings(demo=True)
    with pytest.raises(ValidationError):
        Settings(public_origin="http://localhost:8443")


@pytest.mark.parametrize("options", [
    {"max_tokens": 1025}, {"max_tokens": 0}, {"max_tokens": True},
    {"max_completion_tokens": 10}, {"model": "arbitrary-model"},
    {"stream": True},
])
def test_provider_authority_and_output_budget_cannot_be_overridden(tmp_path, options):
    token = tmp_path / "credential"
    token.write_text("policy_only_not_a_provider_credential")
    token.chmod(0o600)
    client = VultrClient(Settings(model_id="policy_assertion", inference_key_file=token))
    with pytest.raises(ProviderFailure, match="PROVIDER_OPTIONS_INVALID"):
        client.complete([], **options)
    assert client.calls == 0


def test_secret_file_must_be_private_owned_regular_file(tmp_path):
    secret = tmp_path / "credential"
    secret.write_text("unit_assertion_only\n")
    secret.chmod(0o600)
    assert read_secret(secret) == "unit_assertion_only"
    secret.chmod(0o644)
    with pytest.raises(ValueError):
        read_secret(secret)
    secret.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(secret)
    with pytest.raises(OSError):
        read_secret(link)


def test_unknown_model_authority_fields_are_rejected():
    with pytest.raises(ProviderFailure):
        require_json_object({"content": '{"capability":"text","approved":true}'}, {"capability"})
    with pytest.raises(ProviderFailure):
        require_json_object({"content": "not JSON"}, {"capability"})


def test_real_sqlite_rollback_and_online_backup(tmp_path):
    assert tuple(int(x) for x in assert_runtime().split(".")) >= (3, 51, 3)
    live = connect(tmp_path / "live.sqlite")
    backup = connect(tmp_path / "restored.sqlite")
    try:
        live.execute("CREATE TABLE assertion (value INTEGER NOT NULL)")
        live.execute("BEGIN IMMEDIATE")
        live.execute("INSERT INTO assertion VALUES (42)")
        live.execute("ROLLBACK")
        assert live.execute("SELECT count(*) FROM assertion").fetchone()[0] == 0
        live.execute("INSERT INTO assertion VALUES (17)")
        live.backup(backup)
        assert backup.execute("SELECT value FROM assertion").fetchone()[0] == 17
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        live.close()
        backup.close()


def test_empty_gate_cannot_claim_success(tmp_path):
    report = gate_report(Settings(data_dir=tmp_path))
    assert report["status"] == "pending"
    assert all(check["status"] == "pending" for check in report["checks"].values())


def test_cli_missing_source_fails_without_exposing_local_data(tmp_path):
    environment = {k: v for k, v in os.environ.items() if not k.startswith("LATCH_")}
    environment["LATCH_DATA_DIR"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "services.common.preflight", "source"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "failed"
    assert str(tmp_path) not in result.stdout
    assert result.stderr == ""
    assert Path(tmp_path / "p0/source.json").stat().st_mode & 0o077 == 0
