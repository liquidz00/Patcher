---
description: "Assembled Patcher workflows: Slack DM patch summary to a CISO, CI gate that blocks merges when adoption drops, structured-log export to Datadog or Scanner, public-catalog CSV walk, and Installomator label generation for Cask-only titles via valuesfromarguments."
---

(recipes)=

# Recipes

:::{rst-class} lead
Assembled scripts that combine fetch, analyze, and export into complete programs.
:::

The per-command pages ({doc}`export`, {doc}`analyze`) document one thing in isolation. The recipes below combine `fetch_patches`, `export`, `analyze`, and {class}`~patcher.clients.patcher_api.PatcherAPIClient` into complete programs you'd actually deploy.

## Sending Summaries via Slack DM

Say you wanted to message your CISO weekly with patch reports; here's how. Following recipe posts directly to a Slack user (not a channel) using a Slack Bot Token and Block Kit formatting.

```python
import asyncio
import os

import httpx
from patcher import PatcherClient

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
CISO_USER_ID = os.environ["CISO_SLACK_USER_ID"]  # e.g. "U01ABCD2EFG"


async def main() -> None:
    async with PatcherClient(
        client_id=os.environ["JAMF_CLIENT_ID"],
        client_secret=os.environ["JAMF_CLIENT_SECRET"],
        server=os.environ["JAMF_URL"],
    ) as client:
        titles = await client.fetch_patches()

    healthy = sum(1 for t in titles if t.completion_percent >= 90)
    at_risk = [t for t in titles if t.completion_percent < 70]
    at_risk.sort(key=lambda t: t.completion_percent)

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "Daily Patch Summary"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Titles tracked*\n{len(titles)}"},
                {"type": "mrkdwn", "text": f"*≥90% deployed*\n{healthy}"},
                {"type": "mrkdwn", "text": f"*Below 70%*\n{len(at_risk)}"},
            ],
        },
    ]

    if at_risk:
        worst = "\n".join(
            f"• *{t.title}* — {t.completion_percent:.0f}% "
            f"({t.hosts_patched}/{t.total_hosts})"
            for t in at_risk[:5]
        )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Worst 5*\n{worst}"},
        })

    httpx.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        json={"channel": CISO_USER_ID, "blocks": blocks},
    ).raise_for_status()


if __name__ == "__main__":
    asyncio.run(main())
```

Env vars required: `JAMF_CLIENT_ID`, `JAMF_CLIENT_SECRET`, `JAMF_URL`, `SLACK_BOT_TOKEN`, `CISO_SLACK_USER_ID`. The bot needs the `chat:write` scope and must be installed to the workspace. To DM a user, pass their user ID (`U…`) as the `channel`; Slack opens the IM conversation automatically.

```{tip}
Channel-wide alerting (a `#patch-state` channel rather than a person's DMs) is the same recipe, swap `CISO_SLACK_USER_ID` for a channel ID (`C…`) or name (`#patch-state`). For a one-line incident bridge, post a Block Kit `actions` block with a button linking to the HTML report URL.
```

## Logging tool export (Datadog, Scanner, generic HTTP intake)

Stream patch state to a logging platform as structured log events. The example below targets Datadog's HTTP intake; [Scanner](https://scanner.dev) and any other HTTP-intake log platform accept the same shape if you swap the URL and auth header.

```python
import asyncio
import os
from datetime import datetime, timezone

import httpx
from patcher import PatcherClient

DD_API_KEY = os.environ["DATADOG_API_KEY"]
DD_INTAKE = "https://http-intake.logs.datadoghq.com/api/v2/logs"
SERVICE = "patcher"


async def main() -> None:
    async with PatcherClient(
        client_id=os.environ["JAMF_CLIENT_ID"],
        client_secret=os.environ["JAMF_CLIENT_SECRET"],
        server=os.environ["JAMF_URL"],
    ) as client:
        titles = await client.fetch_patches()

    now = datetime.now(timezone.utc).isoformat()
    events = [
        {
            "ddsource": SERVICE,
            "service": SERVICE,
            "ddtags": "env:prod,team:macadmin",
            "hostname": "patcher",
            "timestamp": now,
            "message": f"{t.title} at {t.completion_percent:.1f}%",
            "patch_title": t.title,
            "completion_percent": t.completion_percent,
            "hosts_patched": t.hosts_patched,
            "missing_patch": t.missing_patch,
            "total_hosts": t.total_hosts,
            "latest_version": t.latest_version,
        }
        for t in titles
    ]

    httpx.post(
        DD_INTAKE,
        headers={"DD-API-KEY": DD_API_KEY, "Content-Type": "application/json"},
        json=events,
        timeout=30.0,
    ).raise_for_status()
    print(f"Shipped {len(events)} events")


if __name__ == "__main__":
    asyncio.run(main())
```

Patch state becomes queryable as structured logs (`service:patcher AND completion_percent:<50`), graphable as facets, and alertable via the platform's native monitor rules. For Scanner, swap `DD_INTAKE` for the Scanner ingest URL and the header for `Authorization: Bearer <scanner-token>`. The event shape itself is generic JSON.

```{note}
Datadog's HTTP intake has a 5 MB body cap and 1 000 events per batch. A typical Patcher run is well under both ceilings, but batch if you're tracking thousands of titles. The same caveat applies to most log-intake APIs.
```

## Generate an Installomator label for a Cask-only title

The Patcher catalog stitches Homebrew Cask, Installomator, AutoPkg, JAI, and MAS into one view. For apps that exist in Cask but have no Installomator label, the catalog's `generate-label` endpoint projects Cask's metadata into a label-shaped object. You can pipe that into Installomator's {ghwiki}`valuesfromarguments <Installomator:Configuration-and-Variables#install-without-a-label>` mode to install the app without writing a real label first.

```python
"""Print a runnable Installomator command for any catalog slug.

Usage: python generate_label.py <slug>
Example: python generate_label.py figma
"""
import asyncio
import shlex
import sys

from patcher import PatcherAPIClient

REQUIRED = ("name", "type", "downloadURL", "expectedTeamID")


async def main(slug: str) -> int:
    async with PatcherAPIClient() as api:
        label = await api.generate_label(slug)

    if label is None:
        print(f"Error: no catalog entry for slug '{slug}'", file=sys.stderr)
        return 1

    missing = [k for k in REQUIRED if not label.content.get(k)]
    if missing:
        print(
            f"Error: cannot build valuesfromarguments invocation for '{slug}'; "
            f"missing required field(s): {', '.join(missing)}",
            file=sys.stderr,
        )
        for warning in label.warnings:
            print(f"  warning: {warning}", file=sys.stderr)
        return 2

    args = [f"{key}={shlex.quote(value)}" for key, value in label.content.items()]
    sources = ", ".join(label.sources_used)
    print(f"# Generated from Patcher catalog ({sources})")
    for warning in label.warnings:
        print(f"# warning: {warning}")
    print("./Installomator.sh valuesfromarguments \\\n  " + " \\\n  ".join(args))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python generate_label.py <slug>", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1])))
```

Example invocation and output for a Cask-only title:

```{code-block} console
$ python generate_label.py figma
# Generated from Patcher catalog (homebrew_cask)
./Installomator.sh valuesfromarguments \
  name=Figma \
  type=dmg \
  downloadURL=https://desktop.figma.com/mac/Figma.zip \
  expectedTeamID=T8RA8NE3B7
```

The endpoint's most common warning is missing `expectedTeamID` for Cask-only apps; Cask metadata doesn't include the developer Team ID, so a Cask-only slug will surface a warning if it can't be inferred. See {ghwiki}`the Installomator wiki <Installomator:Configuration-and-Variables>` for the full set of variables Installomator accepts and {ghwiki}`Tutorial 3 <Installomator:Tutorial-3-for-a-label-with-a-bad-versioning>` for an example of when `valuesfromarguments` is the right tool.
