---
description: "Call the hosted Patcher catalog API at api.patcherctl.dev: what it is for, representative read requests for any language, and how to run your own instance."
---

(api-guides)=

# Using the API

:::{rst-class} lead
Query the stitched macOS app catalog over plain HTTP, from any language.
:::

---

The Patcher API is a public, read-only catalog of macOS app patching metadata, stitched from Installomator, Homebrew Cask, AutoPkg, and Jamf App Installers into one canonical record per app. The {doc}`library <library>` talks to **your** Jamf instance, the API serves the *shared* upstream catalog that Patcher matches against.

::::{highlights}
{iconify}`octicon:terminal-16` Outside Python
: You want catalog data from a shell script, or another language.

{iconify}`octicon:package-16` Catalog lookups
: You need the app metadata for an app without standing up your own ingestion.

{iconify}`octicon:git-compare-16` Drift and labels
: You want to check cross-source version drift, or generate Installomator-shaped labels.
::::

:::{seealso}

{iconify}`material-icon-theme:swagger` [Swagger Docs](https://api.patcherctl.dev/docs)  |  {iconify}`material-icon-theme:document` [Redoc](https://api.patcherctl.dev/redoc)  |  {iconify}`material-icon-theme:openapi` [OpenAPI Schema](https://api.patcherctl.dev/openapi.json)
:::

## Common Requests

The catalog is plain HTTP, so reach it from whatever you already script in. Each tab runs the same four calls: list the catalog, pull one app's version and download URL, generate an Installomator label, and check for cross-source version drift. The `patcher` package ships a typed wrapper, {class}`~patcher.clients.patcher_api.PatcherAPIClient` (its own tab below); everyone else hits the URLs directly.

::::{tab-set}

:::{tab-item} {iconify}`mdi:bash` Bash
:sync: bash

```bash
#!/bin/bash

BASE="https://api.patcherctl.dev"

# List the first page of the catalog
curl -sS "$BASE/apps?limit=10" | jq .

# One app's current version and download URL
curl -sS "$BASE/apps/firefox" | jq '{version: .current_version, url: .download_url}'

# Generate an Installomator label
curl -sS -X POST "$BASE/apps/firefox/generate-label" | jq .

# Check cross-source version drift (null if no drift)
curl -sS "$BASE/apps/firefox/drift" | jq .
```
:::

:::{tab-item} {iconify}`material-icon-theme:python` Python
:sync: python

```python
import httpx

BASE = "https://api.patcherctl.dev"

with httpx.Client(base_url=BASE) as client:
    # List the first page of the catalog
    apps = client.get("/apps", params={"limit": 10}).json()

    # One app's current version and download URL
    firefox = client.get("/apps/firefox").json()
    print(firefox["current_version"], firefox["download_url"])

    # Generate an Installomator label
    label = client.post("/apps/firefox/generate-label").json()
    print(label["content"])

    # Check cross-source version drift (None if no drift)
    drift = client.get("/apps/firefox/drift").json()
    if drift:
        print(drift["leader"], "leads", drift["laggard"])
```
:::

:::{tab-item} <span class="patcher-tab-icon"></span> PatcherAPIClient
:sync: patcher

The `patcher` package wraps every endpoint with typed Pydantic models, so you get attribute access (`app.current_version`) and editor autocomplete. Methods return `None` rather than raising when a slug isn't found.

```python
from patcher import PatcherAPIClient

async with PatcherAPIClient() as api:
    # List the first page of the catalog
    apps = await api.list_apps(limit=10)

    # One app's current version and download URL
    firefox = await api.get_app("firefox")
    print(firefox.current_version, firefox.download_url)

    # Generate an Installomator label
    label = await api.generate_label("firefox")
    print(label.content)

    # Check cross-source version drift (None if no drift)
    drift = await api.get_app_drift("firefox")
    if drift:
        print(f"{drift.leader} leads {drift.laggard}")
```
:::

:::{tab-item} {iconify}`material-icon-theme:javascript` JavaScript
:sync: javascript

```javascript
const BASE = "https://api.patcherctl.dev";

// List the first page of the catalog
const apps = await fetch(`${BASE}/apps?limit=10`).then((r) => r.json());

// One app's current version and download URL
const firefox = await fetch(`${BASE}/apps/firefox`).then((r) => r.json());
console.log(firefox.current_version, firefox.download_url);

// Generate an Installomator label
const label = await fetch(`${BASE}/apps/firefox/generate-label`, {
  method: "POST",
}).then((r) => r.json());
console.log(label.content);

// Check cross-source version drift (null if no drift)
const drift = await fetch(`${BASE}/apps/firefox/drift`).then((r) => r.json());
if (drift) console.log(`${drift.leader} leads ${drift.laggard}`);
```
:::

:::{tab-item} {iconify}`material-icon-theme:swift` Swift
:sync: swift

```swift
import Foundation

func get(_ path: String) async throws -> Any {
    let url = URL(string: "https://api.patcherctl.dev\(path)")!
    let (data, _) = try await URLSession.shared.data(from: url)
    return try JSONSerialization.jsonObject(with: data)
}

// List the first page of the catalog
let apps = try await get("/apps?limit=10")

// One app's current version and download URL
let firefox = try await get("/apps/firefox") as! [String: Any]
print(firefox["current_version"] ?? "", firefox["download_url"] ?? "")

// Generate an Installomator label (POST)
var request = URLRequest(url: URL(string: "https://api.patcherctl.dev/apps/firefox/generate-label")!)
request.httpMethod = "POST"
let (labelData, _) = try await URLSession.shared.data(for: request)
let label = try JSONSerialization.jsonObject(with: labelData) as! [String: Any]
print(label["content"] ?? "")

// Check cross-source version drift (null if no drift)
if let drift = try await get("/apps/firefox/drift") as? [String: Any] {
    print(drift["leader"] ?? "", "leads", drift["laggard"] ?? "")
}
```
:::

:::{tab-item} {iconify}`material-icon-theme:ruby` Ruby
:sync: ruby

```ruby
require "net/http"
require "json"

BASE = "https://api.patcherctl.dev"

# List the first page of the catalog
apps = JSON.parse(Net::HTTP.get(URI("#{BASE}/apps?limit=10")))

# One app's current version and download URL
firefox = JSON.parse(Net::HTTP.get(URI("#{BASE}/apps/firefox")))
puts firefox["current_version"], firefox["download_url"]

# Generate an Installomator label
label = JSON.parse(Net::HTTP.post(URI("#{BASE}/apps/firefox/generate-label"), "").body)
puts label["content"]

# Check cross-source version drift (nil if no drift)
drift = JSON.parse(Net::HTTP.get(URI("#{BASE}/apps/firefox/drift")))
puts "#{drift['leader']} leads #{drift['laggard']}" if drift
```
:::

::::

A `404` (with a `detail` field) means the slug isn't in the catalog. For the full cookbook, source payloads, drift, pagination, ETag revalidation, and error shapes, see {doc}`/reference/api/examples`.

## Caching

The catalog only changes when a fresh build deploys, usually once a day. So most of the time, the data you fetched earlier is still current and you don't need to download it again. Two things make that cheap.

### ETags

:::{definition} ETag
A short fingerprint of the catalog's current state, returned in a response header. Send it back on your next request and the API tells you whether anything changed, so you can skip re-downloading data you already have.
:::

::::{steps}

:::{step} Save the ETag

Your first response includes a header like `ETag: "a1b2c3..."`. Hold onto that value (and the response body).
:::

:::{step} Send it back

On your next request, add the header `If-None-Match: "a1b2c3..."`.
:::

:::{step} Check the status code

`304 Not Modified` means nothing changed, so reuse the copy you already have (the response body is empty). `200 OK` means the catalog moved, so use the fresh body and save its new ETag.
:::
::::

### Cloudflare

The API sits behind Cloudflare's edge cache, so even a plain request usually resolves from a server near you instead of the origin. You get fast responses without doing anything.

:::{seealso}
For a worked ETag round-trip in `curl`, see {doc}`/reference/api/examples`.
:::

## Running Your Own

The hosted instance is the easiest path, but the API is open source and self-hostable. To run your own catalog (your own ingestion schedule, your own data, or an air-gapped deployment), see {doc}`/project/self-hosting`. `PatcherAPIClient` accepts a `base_url=` override to point at a self-hosted instance or a local `make serve-api` run.
