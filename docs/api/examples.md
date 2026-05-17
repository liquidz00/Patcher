# Examples

:::{rst-class} lead
End-to-end `curl` and `httpx` (Python) examples for talking to the Patcher API.
:::

```{note}
A dedicated `PatcherAPIClient` helper class is on the roadmap. Until then, the patterns below are the recommended shape: a thin wrapper around `httpx` from Python, or `curl` from any shell. Both are minimal enough that a custom integration can lift them as-is.
```

## Setup

Stash your token in an environment variable so it doesn't end up in shell history or source control.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`devicon:bash` bash
:sync: bash

```bash
export PATCHER_API_TOKEN="<the-token-you-received>"
export PATCHER_API_URL="https://api.patcherctl.dev"
```

::::

::::{tab-item} {iconify}`devicon:python` python
:sync: python

```python
import os
import httpx

API_URL = "https://api.patcherctl.dev"
TOKEN = os.environ["PATCHER_API_TOKEN"]

client = httpx.Client(
    base_url=API_URL,
    headers={"Authorization": f"Bearer {TOKEN}"},
    timeout=30.0,
)
```

::::
:::::

## List apps

The simplest call returns the first page of the catalog.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`devicon:bash` bash
:sync: bash

```bash
curl -sS \
  -H "Authorization: Bearer ${PATCHER_API_TOKEN}" \
  "${PATCHER_API_URL}/apps?limit=10" | jq .
```

::::

::::{tab-item} {iconify}`devicon:python` python
:sync: python

```python
response = client.get("/apps", params={"limit": 10})
response.raise_for_status()
apps = response.json()
for app in apps:
    print(app["slug"], app["current_version"])
```

::::
:::::

## Filter by source

Find every app surfaced by Installomator that is also in the Homebrew Cask catalog.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`devicon:bash` bash
:sync: bash

```bash
curl -sS \
  -H "Authorization: Bearer ${PATCHER_API_TOKEN}" \
  "${PATCHER_API_URL}/apps?source=installomator&limit=1000" \
  | jq '[.[] | select(.sources | index("homebrew_cask"))] | length'
```

::::

::::{tab-item} {iconify}`devicon:python` python
:sync: python

response = client.get(
    "/apps",
    params={"source": "installomator", "limit": 1000},
)
response.raise_for_status()
both = [a for a in response.json() if "homebrew_cask" in a["sources"]]
print(f"{len(both)} apps in both Installomator and Cask")
```

```{note}
The `source` and `exclude_source` filters compose. Querying `?source=installomator&exclude_source=homebrew_cask` would return Installomator apps that have **no** Cask coverage. The filter is applied server-side before pagination, so `limit` reflects the filtered result count rather than a pre-filter slice.
```

::::
:::::

## Fetch a single app

Returns `404` if the slug isn't in the catalog.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`devicon:bash` bash
:sync: bash

```bash
curl -sS \
  -H "Authorization: Bearer ${PATCHER_API_TOKEN}" \
  "${PATCHER_API_URL}/apps/firefox" | jq .
```

::::

::::{tab-item} {iconify}`devicon:python` python
:sync: python

```python
response = client.get("/apps/firefox")
if response.status_code == 404:
    print("Not in catalog")
else:
    response.raise_for_status()
    app = response.json()
    print(app["current_version"], app["download_url"])
```

::::
:::::

## Per-source payloads

Useful for tooling that wants the original upstream data (Homebrew Cask JSON, the raw Installomator label, AutoPkg recipe pointers) rather than the projected `apps` row.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`devicon:bash` bash
:sync: bash

```bash
curl -sS \
  -H "Authorization: Bearer ${PATCHER_API_TOKEN}" \
  "${PATCHER_API_URL}/apps/firefox/sources" | jq .
```

::::

::::{tab-item} {iconify}`devicon:python` python
:sync: python

```python
response = client.get("/apps/firefox/sources")
response.raise_for_status()
sources = response.json()
# Source values are null when that source didn't contribute.
if sources["installomator"]:
    print("Installomator label:", sources["installomator"]["label_name"])
if sources["homebrew_cask"]:
    print("Cask token:", sources["homebrew_cask"]["token"])
if sources["autopkg"]:
    print(f"{len(sources['autopkg']['recipes'])} AutoPkg recipes")
```

::::
:::::

## Generate an Installomator label

Projects an app's Cask + Installomator source data into a label-shaped dict you can drop into your Installomator deployment.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`devicon:bash` bash
:sync: bash

```bash
curl -sS -X POST \
  -H "Authorization: Bearer ${PATCHER_API_TOKEN}" \
  "${PATCHER_API_URL}/apps/firefox/generate-label" | jq .
```

::::

::::{tab-item} {iconify}`devicon:python` python
:sync: python

```python
response = client.post("/apps/firefox/generate-label")
response.raise_for_status()
label = response.json()

print(f"# Generated label: {label['label_name']}")
print(f"# Sources used: {', '.join(label['sources_used'])}")
for warning in label["warnings"]:
    print(f"# WARN: {warning}")
for key, value in label["content"].items():
    print(f'{key}="{value}"')
```

::::
:::::

The endpoint returns a `warnings` array surfacing fields that couldn't be resolved. The most common warning is missing `expectedTeamID` for Cask-only apps, since Cask metadata doesn't include the developer Team ID.

## Use the ETag to skip unchanged downloads

Every read response carries an `ETag` whose value is the SHA-256 of the underlying catalog DB. The hash changes exactly when a fresh catalog deploys (typically once per day). Clients that store the ETag from the first response and send it back on subsequent requests get a `304 Not Modified` short-circuit when nothing has changed — no body transfer, no DB read on the server.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`devicon:bash` bash
:sync: bash

```bash
# First request: store the ETag
ETAG=$(curl -sS -D - -o /tmp/apps.json \
  -H "Authorization: Bearer ${PATCHER_API_TOKEN}" \
  "${PATCHER_API_URL}/apps" \
  | awk '/^[Ee][Tt][Aa][Gg]:/ {print $2}' | tr -d '\r')

# Later: revalidate. 304 means our /tmp/apps.json is still current.
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer ${PATCHER_API_TOKEN}" \
  -H "If-None-Match: ${ETAG}" \
  "${PATCHER_API_URL}/apps"
```

::::

::::{tab-item} {iconify}`devicon:python` python
:sync: python

```python
cached_etag: str | None = None
cached_body: list[dict] | None = None

def fetch_apps() -> list[dict]:
    global cached_etag, cached_body
    headers = {}
    if cached_etag:
        headers["If-None-Match"] = cached_etag
    response = client.get("/apps", headers=headers)
    if response.status_code == 304:
        # Catalog hasn't changed; our cache is still valid.
        return cached_body
    response.raise_for_status()
    cached_etag = response.headers.get("ETag")
    cached_body = response.json()
    return cached_body
```

::::
:::::

## Pagination

Walk the full catalog with `limit` + `offset`. Results are deterministically ordered by `slug`, so paging is consistent across calls within the same catalog version.

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`devicon:bash` bash
:sync: bash

```bash
offset=0
limit=200
while :; do
    page=$(curl -sS \
      -H "Authorization: Bearer ${PATCHER_API_TOKEN}" \
      "${PATCHER_API_URL}/apps?limit=${limit}&offset=${offset}")
    count=$(echo "$page" | jq 'length')
    [ "$count" -eq 0 ] && break
    echo "$page" | jq -c '.[]'
    offset=$((offset + limit))
done
```

::::

::::{tab-item} {iconify}`devicon:python` python
:sync: python

```python
def iter_all_apps(page_size: int = 200):
    offset = 0
    while True:
        response = client.get(
            "/apps",
            params={"limit": page_size, "offset": offset},
        )
        response.raise_for_status()
        page = response.json()
        if not page:
            return
        yield from page
        offset += page_size

for app in iter_all_apps():
    print(app["slug"])
```

::::
:::::

## Error handling

All non-2xx responses are JSON with a `detail` field. The most common shapes:

:::::{tab-set}
:sync-group: lang

::::{tab-item} {iconify}`devicon:bash` bash
:sync: bash

```bash
# 401 if the token is missing, invalid, or revoked
$ curl -sS -o /dev/null -w "%{http_code}\n" "${PATCHER_API_URL}/apps"
401

# 404 if the slug isn't in the catalog
$ curl -sS \
    -H "Authorization: Bearer ${PATCHER_API_TOKEN}" \
    "${PATCHER_API_URL}/apps/no-such-app"
{"detail":"App with slug 'no-such-app' not found"}

# 422 if a query parameter is out of range
$ curl -sS \
    -H "Authorization: Bearer ${PATCHER_API_TOKEN}" \
    "${PATCHER_API_URL}/apps?limit=99999" | jq .detail
```

::::

::::{tab-item} {iconify}`devicon:python` python
:sync: python

```python
from httpx import HTTPStatusError

try:
    response = client.get("/apps/no-such-app")
    response.raise_for_status()
except HTTPStatusError as exc:
    detail = exc.response.json().get("detail", "(no detail)")
    print(f"{exc.response.status_code}: {detail}")
```

::::
:::::
