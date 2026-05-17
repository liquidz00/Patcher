# Endpoints

:::{rst-class} lead
Authentication, available endpoints, response shapes, and caching semantics for the Patcher API.
:::

```{important}
The Patcher API is currently in **private beta**. Request access by reaching out on the [#patcher channel](https://macadmins.slack.com/archives/C07EH1R7LB0) in MacAdmins Slack. There's no self-service token issuance yet; tokens are minted manually for early adopters.
```

## Base URL

```
https://api.patcherctl.dev
```

The API is served behind a Cloudflare named tunnel terminating TLS at Cloudflare's edge. All requests are HTTPS. Status pages, OpenAPI schema, and Swagger UI live at the well-known paths described below.

## Authentication

Every endpoint under `/apps` requires a Bearer token. Tokens are stored as SHA-256 hashes server-side; the plaintext is shown once at grant time. If you lose it, request a new one.

```{code-block} http
:caption: Required header on every request

Authorization: Bearer <your-token>
```

Missing, malformed, revoked, or unknown tokens return `401 Unauthorized` with `WWW-Authenticate: Bearer` per RFC 7235.

## Caching

Catalog responses carry an `ETag` whose value is the SHA-256 of the underlying SQLite catalog file. The hash changes exactly when the catalog deploys (typically once per day) and never otherwise, so it's a perfect cache key.

```{code-block} http
:caption: Example response headers

ETag: W/"4f7b...e2a1"
Cache-Control: public, max-age=300, stale-while-revalidate=3600
```

Clients that send `If-None-Match` matching the current ETag get a `304 Not Modified` short-circuit with no body. Cloudflare also caches across users between deploys, so a hot path typically never reaches the origin. Recommended client pattern: store the ETag on first response, send it back on subsequent requests, accept either 200 + new body or 304 + reuse cached body.

ETag headers are applied to `GET` requests under `/apps*` only. `/health` and admin endpoints bypass.

## Endpoints

(get-apps)=

### `GET /apps`

List apps in the catalog with optional filters and pagination.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `vendor` | string | — | Case-insensitive exact vendor match. |
| `source` | string | — | Include only apps whose `sources` array contains this token. |
| `exclude_source` | string | — | Drop apps whose `sources` array contains this token. |
| `limit` | int | `100` | Maximum rows to return. Valid range: `1`–`1000`. |
| `offset` | int | `0` | Number of filtered rows to skip. Valid range: `0`+. |

All filters compose; results are ordered by `slug` so pagination is deterministic across requests.

**Response 200**

```{code-block} json
:caption: Example body (truncated to one record)

[
  {
    "slug": "firefox",
    "bundle_id": "org.mozilla.firefox",
    "name": "Firefox",
    "vendor": "Mozilla",
    "current_version": "150.0.3",
    "latest_release_date": null,
    "download_url": "https://download.mozilla.org/...",
    "install_method": "pkg",
    "sha256": null,
    "sources": ["installomator", "homebrew_cask", "autopkg"],
    "cves": []
  }
]
```

**Sources** is an array describing which upstream catalogs surface this app. Values land in a fixed canonical order: `installomator`, `homebrew_cask`, `autopkg`, `jamf_app_installer`, `mas`. An app's presence in a given source means catalog data was contributed from that ecosystem; the per-source payloads are available via {ref}`GET /apps/{slug}/sources <get-app-sources>`.

(get-app)=

### `GET /apps/{slug}`

Fetch a single app by its slug. Returns `404` if the slug isn't in the catalog.

**Response 200**: same shape as a single item from `GET /apps`.

**Response 404**:

```{code-block} json
{
  "detail": "App with slug 'foo' not found"
}
```

(get-app-sources)=

### `GET /apps/{slug}/sources`

Return the per-source payloads contributing to an app. Each source's value is the upstream catalog's native shape, preserved verbatim. Consumers see the original data, not a normalized projection.

**Response 200**

```{code-block} json
:caption: Example body. Source values are null when that source didn't contribute.

{
  "installomator": {
    "label_name": "firefoxpkg",
    "label_url": "https://github.com/Installomator/.../firefoxpkg.sh",
    "raw": { "name": "Firefox", "type": "pkg", "...": "..." }
  },
  "homebrew_cask": {
    "token": "firefox",
    "cask_json": { "token": "firefox", "name": ["Mozilla Firefox"], "...": "..." }
  },
  "autopkg": {
    "recipes": [
      {
        "identifier": "com.github.autopkg.download.Firefox",
        "name": "Firefox",
        "shortname": "Firefox.download",
        "repo": "autopkg/recipes",
        "path": "Mozilla/Firefox.download.recipe",
        "parent_identifier": null,
        "inferred_type": "download",
        "recipe_url": "https://github.com/autopkg/recipes/blob/master/Mozilla/Firefox.download.recipe"
      }
    ]
  },
  "mas": null,
  "jamf_app_installer": null
}
```

Useful for callers that want to author Installomator labels by hand against the upstream Cask metadata, drive AutoPkg recipe execution, etc.

(post-generate-label)=

### `POST /apps/{slug}/generate-label`

Generate an Installomator label fragment for `slug`. Projects the app's Homebrew Cask and Installomator source payloads into a label-shaped dict consumers can drop into their Installomator deployments.

**Response 200**

```{code-block} json
{
  "label_name": "firefox",
  "sources_used": ["installomator", "homebrew_cask"],
  "content": {
    "name": "Mozilla Firefox",
    "type": "pkg",
    "packageID": "org.mozilla.firefox",
    "downloadURL": "https://download.mozilla.org/...",
    "appNewVersion": "150.0.3",
    "expectedTeamID": "43AQ936H96",
    "blockingProcesses": ["firefox"]
  },
  "warnings": []
}
```

`warnings` surfaces fields that couldn't be resolved (most commonly `expectedTeamID` for Cask-only apps, since Cask metadata doesn't include the developer Team ID).

**Response 404** if the slug doesn't exist.

**Response 422** if the app exists but has no source detail to project from (typically a leftover seed record).

## Errors

| Status | Meaning |
|---|---|
| `200` | OK; response body is the resource. |
| `304` | Not Modified; client's `If-None-Match` matched the current ETag. No body. |
| `401` | Missing, invalid, or revoked bearer token. |
| `404` | Slug doesn't exist in the catalog. |
| `413` | Body too large (admin endpoints only). |
| `422` | Request validated but couldn't be completed (e.g. app has no source detail). |

All error responses follow FastAPI's standard `{"detail": "..."}` shape.

## OpenAPI schema

The full OpenAPI 3.1 schema, including all parameter constraints and exact response shapes, is served at:

```
https://api.patcherctl.dev/openapi.json
```

Swagger UI (interactive) is at `/docs`. ReDoc is at `/redoc`.
