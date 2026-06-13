---
description: "End-to-end curl and PatcherAPIClient examples for the Patcher API. Covers filtering, pagination, ETag revalidation, label generation, and error shapes."
---

# Examples

:::{rst-class} lead
End-to-end `curl` and {class}`~patcher.clients.patcher_api.PatcherAPIClient` examples for talking to the Patcher API.
:::

---

```{note}
The catalog is public, no authentication required. Examples below talk to `api.patcherctl.dev`. Python users should reach for {class}`~patcher.clients.patcher_api.PatcherAPIClient` from the `patcher` package, which wraps the same endpoints with typed Pydantic models. If you can't take the `patcher` dependency, the raw HTTP shape is straightforward; see the `bash` tabs (or use `httpx` / `requests` with the same URLs and params).
```

## Setup

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`mdi:bash` bash
:sync: bash

```bash
export PATCHER_API_URL="https://api.patcherctl.dev"
```

::::

::::{tab-item} {iconify}`material-icon-theme:python` python
:sync: python

```python
import asyncio
from patcher import PatcherAPIClient

async def main():
    async with PatcherAPIClient() as api:
        # examples below assume they run inside this block
        ...

asyncio.run(main())
```

`PatcherAPIClient()` defaults to `https://api.patcherctl.dev`. Override `base_url=` for a self-hosted deployment or a local `make serve-api` instance.

::::
:::::

## List apps

The simplest call returns the first page of the catalog.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`mdi:bash` bash
:sync: bash

```bash
curl -sS "${PATCHER_API_URL}/apps?limit=10" | jq .
```

::::

::::{tab-item} {iconify}`material-icon-theme:python` python
:sync: python

```python
apps = await api.list_apps(limit=10)
for app in apps:
    print(app.slug, app.current_version)
```

`list_apps` returns `list[App]`. The Pydantic model means `app.slug`, `app.current_version`, `app.sources`, etc., are typed attributes rather than dict keys.

::::
:::::

## Filter by source

Find every app surfaced by Installomator that is also in the Homebrew Cask catalog.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`mdi:bash` bash
:sync: bash

```bash
curl -sS "${PATCHER_API_URL}/apps?source=installomator&limit=1000" \
  | jq '[.[] | select(.sources | index("homebrew_cask"))] | length'
```

::::

::::{tab-item} {iconify}`material-icon-theme:python` python
:sync: python

```python
apps = await api.list_apps(source="installomator", limit=1000)
both = [a for a in apps if "homebrew_cask" in a.sources]
print(f"{len(both)} apps in both Installomator and Cask")
```

::::
:::::

```{note}
The `source` and `exclude_source` filters compose. Passing both `source="installomator"` and `exclude_source="homebrew_cask"` returns Installomator apps that have **no** Cask coverage. Filtering is applied server-side before pagination, so `limit` reflects the filtered result count rather than a pre-filter slice.
```

## Fetch a single app

The package method returns `None` on 404 rather than raising. The HTTP endpoint returns a `404` with a `detail` field.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`mdi:bash` bash
:sync: bash

```bash
curl -sS "${PATCHER_API_URL}/apps/firefox" | jq .
```

::::

::::{tab-item} {iconify}`material-icon-theme:python` python
:sync: python

```python
app = await api.get_app("firefox")
if app is None:
    print("Not in catalog")
else:
    print(app.current_version, app.download_url)
```

::::
:::::

## Per-source payloads

Useful for tooling that wants the original upstream data (Homebrew Cask JSON, the raw Installomator label, AutoPkg recipe pointers) rather than the projected `apps` row.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`mdi:bash` bash
:sync: bash

```bash
curl -sS "${PATCHER_API_URL}/apps/firefox/sources" | jq .
```

::::

::::{tab-item} {iconify}`material-icon-theme:python` python
:sync: python

```python
sources = await api.get_app_sources("firefox")
if sources is None:
    return

# Each source attribute is None when that source didn't contribute.
if sources.installomator:
    print("Installomator label:", sources.installomator.label_name)
if sources.homebrew_cask:
    print("Cask token:", sources.homebrew_cask.token)
if sources.autopkg:
    print(f"{len(sources.autopkg.recipes)} AutoPkg recipes")
```

::::
:::::

## Generate an Installomator label

Projects an app's Cask + Installomator source data into a label-shaped object you can drop into your Installomator deployment.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`mdi:bash` bash
:sync: bash

```bash
curl -sS -X POST "${PATCHER_API_URL}/apps/firefox/generate-label" | jq .
```

::::

::::{tab-item} {iconify}`material-icon-theme:python` python
:sync: python

```python
label = await api.generate_label("firefox")
if label is None:
    return

print(f"# Generated label: {label.label_name}")
print(f"# Sources used: {', '.join(label.sources_used)}")
for warning in label.warnings:
    print(f"# WARN: {warning}")
for key, value in label.content.items():
    print(f'{key}="{value}"')
```

::::
:::::

The endpoint returns a `warnings` array surfacing fields that couldn't be resolved. The most common warning is missing `expectedTeamID` for Cask-only apps, since Cask metadata doesn't include the developer Team ID.

## Use the ETag to skip unchanged downloads

Every read response carries an `ETag` whose value is a version token derived from the catalog's newest update timestamp. The token changes exactly when the catalog data changes (typically once per day). Clients that store the ETag from the first response and send it back on subsequent requests get a `304 Not Modified` short-circuit when nothing has changed; no body transfer, no DB read on the server.

```{note}
{class}`~patcher.clients.patcher_api.PatcherAPIClient` does not currently surface ETag caching as a method. The API sits behind Cloudflare, so identical requests typically resolve from edge cache before reaching origin. If you need explicit If-None-Match revalidation, drop to raw HTTP for that specific call.
```

```bash
# First request: store the ETag
ETAG=$(curl -sS -D - -o /tmp/apps.json "${PATCHER_API_URL}/apps" \
  | awk '/^[Ee][Tt][Aa][Gg]:/ {print $2}' | tr -d '\r')

# Later: revalidate. 304 means our /tmp/apps.json is still current.
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "If-None-Match: ${ETAG}" \
  "${PATCHER_API_URL}/apps"
```

## Health check

`/health` is unauthenticated, uncached, and intended for load-balancer probes or simple monitoring. Returns `{"status": "ok"}` when the API is up. Not exposed on {class}`~patcher.clients.patcher_api.PatcherAPIClient`; use raw HTTP if you need to probe.

```bash
curl -sS "${PATCHER_API_URL}/health"
# {"status":"ok"}
```

## Pagination

Walk the full catalog with `limit` + `offset`. Results are deterministically ordered by `slug`, so paging is consistent across calls within the same catalog version.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`mdi:bash` bash
:sync: bash

```bash
offset=0
limit=200
while :; do
    page=$(curl -sS "${PATCHER_API_URL}/apps?limit=${limit}&offset=${offset}")
    count=$(echo "$page" | jq 'length')
    [ "$count" -eq 0 ] && break
    echo "$page" | jq -c '.[]'
    offset=$((offset + limit))
done
```

::::

::::{tab-item} {iconify}`material-icon-theme:python` python
:sync: python

```python
async def iter_all_apps(api: PatcherAPIClient, page_size: int = 200):
    offset = 0
    while True:
        page = await api.list_apps(limit=page_size, offset=offset)
        if not page:
            return
        for app in page:
            yield app
        offset += page_size

async with PatcherAPIClient() as api:
    async for app in iter_all_apps(api):
        print(app.slug)
```

::::
:::::

## Error handling

All non-2xx responses are JSON with a `detail` field. The package wraps these as {exc}`~patcher.core.exceptions.APIResponseError`. `get_app`, `get_app_sources`, and `generate_label` swallow 404 specifically and return `None`; anything else raises.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`mdi:bash` bash
:sync: bash

```bash
# 404 if the slug isn't in the catalog
$ curl -sS "${PATCHER_API_URL}/apps/no-such-app"
{"detail":"App with slug 'no-such-app' not found"}

# 422 if a query parameter is out of range
$ curl -sS "${PATCHER_API_URL}/apps?limit=99999" | jq .detail
```

::::

::::{tab-item} {iconify}`material-icon-theme:python` python
:sync: python

```python
from patcher import APIResponseError

try:
    apps = await api.list_apps(limit=99999)  # over server cap
except APIResponseError as exc:
    # Context is attached as kwargs (status_code, error, url, not_found).
    print(f"{exc.status_code}: {exc.error}")

# 404 is None, not an exception:
missing = await api.get_app("no-such-app")
assert missing is None
```

::::
:::::
