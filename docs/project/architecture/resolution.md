---
description: "How Patcher resolves Installomator labels' dynamic shell expressions across two stages: a Linux ingest server that handles what it safely can, and a self-hosted macOS worker for the rest."
---

(resolution)=

# Resolution

:::{rst-class} lead
How dynamic Installomator label values become concrete versions and URLs.
:::

---

Installomator labels aren't static manifests. They're zsh fragments, and a lot of the values that matter to Patcher (the version, the download URL) are computed by shell expressions that the label expects to run on a real Mac:

```bash
name="Firefox"
type="dmg"
downloadURL=$(curl -fsL "https://download.mozilla.org/?product=firefox-latest-ssl&os=osx&lang=en-US" | sed -n 's/.*"url":"\([^"]*\)".*/\1/p')
appNewVersion=$(curl -fsL "https://product-details.mozilla.org/1.0/firefox_versions.json" | awk -F'"' '/LATEST_FIREFOX_VERSION/ { print $4 }')
expectedTeamID="43AQ936H96"
```

The catalog needs these resolved into concrete values like `https://download.mozilla.org/firefox-118.0.dmg` and `118.0` before clients can use them. But the ingest server isn't on macOS, and running the bash as-is isn't an option (firing `$(curl ...)` at thousands of vendor sites every refresh is slow and unreliable). So Patcher resolves labels in two stages. This page walks through how it works. For the parser, resolver, and ingest source-level reference see {doc}`/reference/api/source/installomator`.

## Two Stages

The work happens in two places. A Linux ingest server resolves everything it safely can, then a self-hosted macOS worker handles the rest. The catalog database is how the two pass work back and forth:

```{mermaid}
flowchart TB
    UP[Installomator labels<br/>on GitHub] --> LIN

    subgraph LIN [Ingest server]
      PARSE[Parser<br/>tokenize bash → fields]
      RES[Resolver<br/>evaluate what's safe]
      ROWS[(app_source_details<br/>resolved + raw)]
      PARSE --> RES --> ROWS
    end

    ROWS -- "raw fragments<br/>still unresolved" --> WORK["/admin/labels/unresolved"]
    WORK --> MAC

    subgraph MAC [self-hosted macOS worker<br/>Temporal]
      EXEC[Installomator.sh<br/>real macOS userspace]
    end

    EXEC -- "POST resolved values" --> POST["/admin/labels/resolved"]
    POST --> ROWS
    ROWS --> STITCH[stitch] --> APPS[(apps)]
```

### Stage 1: On the Linux Ingest Server

When the ingest pipeline pulls labels from Installomator, the parser tokenizes each label into structured fields. The resolver then evaluates as many dynamic fields as it can without leaving the ingest server:

::::{markers}

:::{marker} Pure-shell pipelines
:icon: octicon:check-circle-16
Translate cleanly to native Python (string ops, regex, `sort | uniq`, etc.), so they're evaluated inline.
:::

:::{marker} `$(curl ...)` against the open internet
:icon: octicon:alert-16
Permitted, with strict URL validation and aggressive timeouts. The resolver fetches the URL once and runs the rest of the pipeline on the body.
:::

:::{marker} Fragments needing real macOS userspace
:icon: octicon:skip-16
Anything that needs the macOS userspace (`osascript`, `defaults read`, `getJSONValue` from a binary plist) is skipped. The raw fragment stays in the source-detail row so the macOS worker can pick it up in stage 2.
:::
::::

The resolved values plus the still-raw fragments both land in `app_source_details`. A field that resolved cleanly has its concrete value (e.g. `download_url: "https://download.mozilla.org/firefox-118.0.dmg"`); a field that couldn't has the raw fragment (e.g. `download_url: "$(osascript -e ... )"`).

### Stage 2: On a Self-Hosted macOS Worker

An always-on, self-hosted macOS worker, orchestrated by Temporal, runs continuously. The [worker](https://github.com/liquidz00/patcher-resolver) is open-source and completes the following on each pass:

::::{steps}

:::{step} GETs the worklist

from `/admin/labels/unresolved`. The API returns every label whose `downloadURL` or `appNewVersion` is still a raw shell fragment (or where the macOS worker previously owned the resolved value, so it stays fresh).
:::

:::{step} Runs `Installomator.sh`

against each label name on the worklist. This runs the real Installomator script in a full macOS userspace (codesign, osascript, the lot), capturing the values it computes without installing anything.
:::

:::{step} POSTs the results back

to `/admin/labels/resolved` as NDJSON, one record per label.
:::

::::

The admin endpoint validates each value (URLs must be cleanly-formed `https://`, versions must look like versions, no HTML pages or multi-line junk slipping in), updates the matching `app_source_details` rows, and triggers a re-stitch so the canonical `apps` table reflects the new values. The catalog hash changes, the ETag rotates, downstream caches revalidate.

:::{note} Fallback
A [manually-triggered GitHub Actions workflow](https://github.com/liquidz00/Patcher/blob/main/.github/workflows/resolve-labels.yml) on a hosted macOS runner can perform the same worklist handshake. It exists only as a break-glass path when the self-hosted worker is unavailable, so it never competes with the primary.
:::

## What "User-Context" Labels Means

A small set of Installomator labels resolve from data only the logged-in user has access to (e.g. browser profiles, app-specific user containers). Those are explicitly excluded from the worklist because the headless macOS worker has no logged-in user. Patcher serves them as best-effort with whatever Installomator's metadata declared, and the {doc}`drift detector </reference/api/source/drift>` won't try to compare versions for labels in this category.

## Why This Design

A few alternatives were considered and rejected:

::::{markers}
:icon: octicon:x-circle-16

:::{marker} Run all label evaluation in a single macOS environment
Conceptually simplest, but every refresh of a static label pays the macOS-worker cost. The two-stage split lets the Linux ingest handle the boring majority cheaply.
:::

:::{marker} Run the macOS resolver per-request inside the API
Latency would be unacceptable, and exposing a path that synchronously shells out to vendor sites per request would invite abuse.
:::

:::{marker} Skip dynamic fields entirely
This would cut Patcher's coverage substantially, since a large chunk of Installomator's labels depend on dynamic resolution. The macOS worker exists precisely so that coverage isn't sacrificed.
:::
::::

## What This Looks Like to API Callers

You don't see any of this. The `GET /apps/firefox` response carries a `download_url`, `current_version`, and `install_method` like every other app. Whether those values came from the Linux ingest's inline resolver or from a macOS worker pass doesn't matter to callers. They get clean, concrete values either way.

The only place the split surfaces in the public API is in admin tooling and the `resolution_source` column on `installomator_labels` (a row with `resolution_source = "macos"` was last updated by the macOS worker; `NULL` means the Linux ingest still owns it).
