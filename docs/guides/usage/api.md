---
description: "Call the hosted Patcher catalog API at api.patcherctl.dev: what it is for, representative read requests for any language, and how to run your own instance."
---

(api-guides)=

# Using the API

:::{rst-class} lead
Query the stitched macOS app catalog over plain HTTP, from any language.
:::

---

The Patcher API is a public, read-only catalog of macOS app patching metadata, stitched from Installomator, Homebrew Cask, AutoPkg, and Jamf App Installers into one canonical record per app. It is hosted at `https://api.patcherctl.dev` and needs no authentication for any catalog read. Where the {doc}`library <library>` talks to *your* Jamf instance, the API serves the *shared* upstream catalog that Patcher matches against.

::::{highlights}
{iconify}`octicon:terminal-16` Outside Python
: You want catalog data from a shell script, another language, or a one-off `curl`.

{iconify}`octicon:package-16` Catalog lookups
: You need the current version, download URL, or source coverage for an app without standing up your own ingestion.

{iconify}`octicon:git-compare-16` Drift and labels
: You want to check cross-source version drift, or generate an Installomator-shaped label, programmatically.
::::

## What the API is for

The catalog answers questions like "what is the current version of Firefox," "which sources cover Slack," "do any apps have version drift across sources," and "give me an Installomator label for this app." Python consumers should prefer {class}`~patcher.clients.patcher_api.PatcherAPIClient` from the `patcher` package, which wraps every endpoint with typed Pydantic models. Everyone else talks raw HTTP.

## A couple of requests

List the first page of the catalog:

```{code-block} bash
curl -sS "https://api.patcherctl.dev/apps?limit=10" | jq .
```

Fetch a single app by slug (returns `404` with a `detail` field if the slug is not in the catalog):

```{code-block} bash
curl -sS "https://api.patcherctl.dev/apps/firefox" | jq '.current_version, .download_url'
```

Source and pagination filters compose server-side. For worked examples covering per-source payloads, label generation, ETag revalidation, and error shapes, see {doc}`/reference/api/examples`.

## Caching

Catalog responses carry a weak `ETag` whose value is the SHA-256 of the underlying catalog file. It changes only when a fresh catalog deploys (typically once per day). Store the ETag from your first response and send it back as `If-None-Match` to get a `304 Not Modified` short-circuit when nothing has changed. The API also sits behind Cloudflare, so hot paths usually resolve from edge cache before reaching the origin.

## The full endpoint list

This page is a usage primer, not the spec. The complete set of endpoints, parameter constraints, and response shapes (auto-generated from the live OpenAPI schema) lives in the {doc}`endpoint reference </reference/api/endpoints>`. The raw schema is served at `https://api.patcherctl.dev/openapi.json`, with Swagger UI at `/docs` and ReDoc at `/redoc`.

## Running your own

The hosted instance is the easiest path, but the API is open source and self-hostable. To run your own catalog (your own ingestion schedule, your own data, or an air-gapped deployment), see {doc}`/project/self-hosting`. `PatcherAPIClient` accepts a `base_url=` override to point at a self-hosted instance or a local `make serve-api` run.
