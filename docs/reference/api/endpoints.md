---
description: "Patcher API endpoint reference. Lists, filters, per-source payloads, label generation, ETag caching semantics, and OpenAPI schema location."
---

# Endpoints

:::{rst-class} lead
Read the stitched macOS app catalog without standing up your own ingestion pipeline.
:::

```{note}
The Patcher API catalog is **public** — no authentication required for any `/apps*` endpoint. Admin endpoints used to upload fresh catalog data are gated behind a separate deploy token and not documented publicly.
```

## Base URL

```
https://api.patcherctl.dev
```

The API is served behind a Cloudflare named tunnel terminating TLS at Cloudflare's edge. All requests are HTTPS.

## Caching

Catalog responses carry an `ETag` whose value is the SHA-256 of the underlying SQLite catalog file. The hash changes exactly when the catalog deploys (typically once per day) and never otherwise, so it's a perfect cache key.

```{code-block} text
:caption: Example response headers

ETag: W/"4f7b...e2a1"
Cache-Control: public, max-age=300, stale-while-revalidate=3600
```

Clients that send `If-None-Match` matching the current ETag get a `304 Not Modified` short-circuit with no body. Cloudflare also caches across users between deploys, so a hot path typically never reaches the origin. Recommended client pattern: store the ETag on first response, send it back on subsequent requests, accept either 200 + new body or 304 + reuse cached body.

ETag headers are applied to `GET` requests under `/apps*` only. `/health` and admin endpoints bypass.

## Endpoint reference

The reference below is auto-generated from the live OpenAPI schema. When a route's signature or response model changes in code, this page follows automatically on the next docs build.

```{eval-rst}
.. openapi:: ../_generated/openapi.json
   :paths: /apps /apps/{slug} /apps/{slug}/sources /apps/{slug}/generate-label
   :examples:
```

## Errors

| Status | Meaning |
|---|---|
| `200` | OK; response body is the resource. |
| `304` | Not Modified; client's `If-None-Match` matched the current ETag. No body. |
| `404` | Slug doesn't exist in the catalog. |
| `422` | Request validated but couldn't be completed (e.g. app has no source detail). |

All error responses follow FastAPI's standard `{"detail": "..."}` shape.

## OpenAPI schema

The full OpenAPI 3.1 schema, including all parameter constraints and exact response shapes, is served at:

```
https://api.patcherctl.dev/openapi.json
```

Swagger UI (interactive) is at `/docs`. ReDoc is at `/redoc`. Admin-scoped endpoints are deliberately excluded from the schema and not documented publicly.
