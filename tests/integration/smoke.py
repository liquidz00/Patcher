"""
Manual smoke test for PatcherClient against a real Jamf instance.

Runs hand-curated end-to-end checks against the live Patcher surfaces:
auth, iOS pipeline, Installomator labels, a real ``fetch_patches()`` call,
and a synthetic analyze + export flow. Defaults to Jamf's public dummy
tenant (``dummy.jamfcloud.com``) but can be pointed at any Jamf instance
via the env vars listed below.

This file intentionally omits the ``test_`` prefix so pytest collection
skips it. Run directly::

    uv run python tests/integration/smoke.py

Or via the Makefile shortcut::

    make smoke-test

Override the target instance with::

    PATCHER_INTEGRATION_URL=https://yourtenant.jamfcloud.com \\
    PATCHER_INTEGRATION_CLIENT_ID=... \\
    PATCHER_INTEGRATION_CLIENT_SECRET=... \\
        uv run python tests/integration/smoke.py

Exit code is ``0`` when every check passes, ``1`` when any check fails.
Informational results (e.g., dummy tenant has no patch titles) do not
count as failures.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path

import click

# Patcher's logger has no handlers in library contexts (the CLI is what
# installs file/terminal handlers). Without one, Python falls back to its
# ``lastResort`` StreamHandler at WARNING, which prints library-internal
# messages over our own status output. Attach a NullHandler so library
# logs are swallowed; failures still surface via raised exceptions, which
# our check_* helpers catch and report.
logging.getLogger("Patcher").addHandler(logging.NullHandler())
logging.getLogger("Patcher").propagate = False

# Import via the installed package name. The pytest integration suite
# uses ``from src.patcher import ...`` because pytest adds the project
# root to ``sys.path``; this script runs standalone, so we import the
# normally-resolvable ``patcher`` package instead.
from patcher import PatcherClient
from patcher.core.installomator import InstallomatorClient
from patcher.core.models.patch import PatchTitle

# Same defaults as the integration suite. Credentials are intentionally
# public and documented by Jamf at
# https://developer.jamf.com/jamf-pro/docs/populating-dummy-data
_DUMMY_URL = "https://dummy.jamfcloud.com"
_DUMMY_CLIENT_ID = "2b7ea5e9-cbab-4f60-97e3-32eaefeee768"
_DUMMY_CLIENT_SECRET = "o0dwi8E0XMaYtX760LB05csjHeJoGHKldTi4R5x7NKwLMl25gYenpMAlRDerA6G1"


class Counter:
    """Tracks per-check outcomes and renders pass/fail/info markers."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.info = 0

    def ok(self, msg: str) -> None:
        click.echo("   " + click.style("[OK]", fg="green", bold=True) + f"   {msg}")
        self.passed += 1

    def fail(self, msg: str, exc: BaseException | None = None) -> None:
        click.echo("   " + click.style("[FAIL]", fg="red", bold=True) + f" {msg}")
        if exc is not None:
            click.echo("          " + click.style(f"{type(exc).__name__}: {exc}", fg="red"))
        self.failed += 1

    def note(self, msg: str) -> None:
        click.echo("   " + click.style("[INFO]", fg="blue", bold=True) + f" {msg}")
        self.info += 1


def section(title: str) -> None:
    """Render a section header."""
    click.echo()
    click.echo(click.style(f"== {title} ==", fg="cyan", bold=True))


async def check_auth(patcher: PatcherClient, count: Counter) -> bool:
    """Confirm an OAuth token can be fetched from the configured instance."""
    section("Authentication")
    try:
        token = await patcher.jamf.token_manager.fetch_token()
    except Exception as exc:
        count.fail("Token fetch raised", exc)
        return False

    if token and getattr(token, "token", None):
        # AccessToken model exposes the raw value as ``.token``. Don't
        # print it. ``token.expires`` is a datetime, but the model also
        # exposes a remaining-seconds helper.
        count.ok(f"Access token fetched (expires at {token.expires.isoformat()})")
        return True

    count.fail("Token fetch returned an empty token")
    return False


async def check_ios(patcher: PatcherClient, count: Counter) -> None:
    """Exercise the device-data pipeline that powers ``--ios`` exports."""
    section("iOS device pipeline")
    try:
        ids = await patcher.jamf.get_device_ids()
        count.ok(f"{len(ids)} mobile device IDs returned")
    except Exception as exc:
        count.fail("get_device_ids raised", exc)
        return

    if not ids:
        count.note("No mobile devices in instance; skipping OS-version check")
    else:
        sample = ids[:5]
        try:
            versions = await patcher.jamf.get_device_os_versions(sample)
            count.ok(f"{len(versions)} OS-version entries from {len(sample)} sampled IDs")
        except Exception as exc:
            count.fail("get_device_os_versions raised", exc)

    try:
        sofa = await patcher.jamf.get_sofa_feed()
        if sofa:
            count.ok(f"SOFA feed returned {len(sofa)} OS-version entries")
        else:
            count.note("SOFA feed returned empty list")
    except Exception as exc:
        count.fail("get_sofa_feed raised", exc)


async def check_installomator(count: Counter) -> None:
    """Verify the Installomator label catalog is reachable and parseable."""
    section("Installomator labels")
    iom = InstallomatorClient()
    try:
        try:
            labels = await iom.list_available_labels()
        except Exception as exc:
            count.fail("list_available_labels raised", exc)
            return

        count.ok(f"{len(labels)} labels discovered from Labels.txt")

        if "firefox" not in labels:
            count.fail("Expected 'firefox' in the label set")
            return

        try:
            firefox = await iom.get_label("firefox")
        except Exception as exc:
            count.fail("get_label('firefox') raised", exc)
            return

        if firefox is None:
            count.fail("get_label('firefox') returned None")
        elif firefox.expected_team_id:
            count.ok(f"firefox label parsed (Team ID: {firefox.expected_team_id})")
        else:
            count.fail("firefox label parsed without expected_team_id")
    finally:
        await iom.api.aclose()


async def check_real_patches(patcher: PatcherClient, count: Counter) -> None:
    """Round-trip ``fetch_patches`` against the live instance."""
    section("Real fetch_patches (against live instance)")
    try:
        # Skip Installomator matching to keep the call focused on Jamf
        # transport. We already validated Installomator in check_installomator().
        titles = await patcher.fetch_patches(match_installomator=False)
    except Exception as exc:
        count.fail("fetch_patches raised", exc)
        return

    if titles:
        count.ok(f"{len(titles)} patch titles returned from live instance")
    else:
        count.note("Live instance returned 0 patch titles (expected for dummy tenant)")


def _synthetic_titles() -> list[PatchTitle]:
    """Build a small, deterministic list of PatchTitle objects."""
    return [
        PatchTitle(
            title="Firefox",
            title_id="1",
            released="2026-05-01",
            hosts_patched=85,
            missing_patch=15,
            latest_version="125.0",
        ),
        PatchTitle(
            title="Google Chrome",
            title_id="2",
            released="2026-05-10",
            hosts_patched=120,
            missing_patch=5,
            latest_version="124.0.6367.91",
        ),
        PatchTitle(
            title="Zoom Client for Meetings",
            title_id="3",
            released="2026-04-20",
            hosts_patched=40,
            missing_patch=60,
            latest_version="5.17.11",
        ),
        PatchTitle(
            title="Slack",
            title_id="4",
            released="2026-05-12",
            hosts_patched=95,
            missing_patch=5,
            latest_version="4.38.121",
        ),
        PatchTitle(
            title="Microsoft Edge",
            title_id="5",
            released="2026-05-08",
            hosts_patched=10,
            missing_patch=90,
            latest_version="124.0.2478.80",
        ),
    ]


async def check_synthetic_pipeline(patcher: PatcherClient, count: Counter) -> None:
    """Exercise ``analyze`` + ``export`` against synthetic in-memory titles."""
    section("Synthetic data analyze + export")
    titles = _synthetic_titles()
    count.ok(f"Constructed {len(titles)} synthetic PatchTitle objects")

    if all(t.completion_percent > 0 for t in titles):
        count.ok("completion_percent auto-calculated by Pydantic validator")
    else:
        zeros = [t.title for t in titles if t.completion_percent == 0]
        count.fail(f"Titles with zero completion_percent: {zeros}")

    try:
        most = await patcher.analyze(titles, criteria="most-installed", top_n=3)
        names = [t.title for t in most]
        if len(most) <= 3 and "Google Chrome" in names:
            count.ok(f"analyze(most-installed, top_n=3) -> {names}")
        else:
            count.fail(f"analyze(most-installed) unexpected result: {names}")
    except Exception as exc:
        count.fail("analyze(most-installed) raised", exc)

    try:
        below = await patcher.analyze(titles, criteria="below-threshold", threshold=50.0)
        names = {t.title for t in below}
        expected = {"Zoom Client for Meetings", "Microsoft Edge"}
        if expected.issubset(names):
            count.ok(f"analyze(below-threshold, 50) -> {sorted(names)}")
        else:
            count.fail(f"analyze(below-threshold) missed expected: got {sorted(names)}")
    except Exception as exc:
        count.fail("analyze(below-threshold) raised", exc)

    # Export to non-PDF formats. PDF needs UI config (font paths, header
    # text) which library callers can supply via ``ui_config=`` on
    # PatcherClient, but exercising that here would require fonts on disk.
    # Excel/HTML/JSON validate the full DataFrame + serialization pipeline
    # without that prerequisite.
    with tempfile.TemporaryDirectory(prefix="patcher-smoke-") as tmp:
        out_dir = Path(tmp)
        try:
            exported = await patcher.export(
                titles,
                output_dir=out_dir,
                formats={"excel", "html", "json"},
                report_title="Patcher Smoke Test",
            )
        except Exception as exc:
            count.fail("export raised", exc)
            return

        for fmt in ("excel", "html", "json"):
            path = exported.get(fmt)
            if path is None:
                count.fail(f"{fmt}: missing from export result")
                continue
            p = Path(path)
            if p.exists() and p.stat().st_size > 0:
                count.ok(f"{fmt}: wrote {p.name} ({p.stat().st_size} bytes)")
            else:
                count.fail(f"{fmt}: file missing or empty at {path}")


async def run() -> int:
    url = os.environ.get("PATCHER_INTEGRATION_URL", _DUMMY_URL)
    client_id = os.environ.get("PATCHER_INTEGRATION_CLIENT_ID", _DUMMY_CLIENT_ID)
    client_secret = os.environ.get("PATCHER_INTEGRATION_CLIENT_SECRET", _DUMMY_CLIENT_SECRET)

    click.echo(click.style("Patcher smoke test", fg="magenta", bold=True))
    click.echo(f"Target:    {url}")
    click.echo(f"Client ID: {client_id[:8]}...")

    count = Counter()
    async with PatcherClient(
        client_id=client_id,
        client_secret=client_secret,
        server=url,
    ) as patcher:
        auth_ok = await check_auth(patcher, count)
        if not auth_ok:
            section("Summary")
            click.echo(click.style("   Authentication failed; aborting.", fg="red", bold=True))
            return 1

        await check_ios(patcher, count)
        await check_installomator(count)
        await check_real_patches(patcher, count)
        await check_synthetic_pipeline(patcher, count)

    section("Summary")
    summary = (
        f"   {click.style(f'{count.passed} passed', fg='green', bold=True)}, "
        f"{click.style(f'{count.failed} failed', fg='red', bold=True)}, "
        f"{click.style(f'{count.info} informational', fg='blue', bold=True)}"
    )
    click.echo(summary)
    return 0 if count.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
