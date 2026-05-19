---
description: "Contribute to Patcher: bug reports, feature requests, PR workflow, environment setup with uv, Makefile targets, and integration tests."
---

(contributing_index)=

# Contributing

:::{rst-class} lead
Contributions are welcome and don't require writing Python. Bug reports, feature requests, documentation improvements, and review feedback all move the project forward.
:::

We firmly believe that diverse backgrounds strengthen a product. Share your ideas regardless of your programming experience — half the time the most valuable contribution is naming a problem clearly.

## How to contribute

The shortest path is to **get in touch first**. Open a [bug report](https://github.com/liquidz00/Patcher/issues/new?template=bug_report.yml), [feature request](https://github.com/liquidz00/Patcher/issues/new?template=feature_request.yml), or [feedback issue](https://github.com/liquidz00/Patcher/issues/new?template=feedback.yml) describing what you want to change before writing code. This avoids the "you already shipped the same thing in a branch" problem and lets us scope the change together.

### Pull request workflow

Standard [GitHub flow](https://docs.github.com/en/get-started/using-github/github-flow):

1. [Fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo) the Patcher repository.
2. Clone your fork locally.
3. Branch off `develop` with a descriptive name.
4. Pull the latest `develop` before opening your PR.
5. Open the PR against `develop`.

```{important}
PRs go to the `develop` branch, not `main`. The `main` branch tracks stable releases; ongoing development lands on `develop` and is merged to `main` as part of the release cut. Tests must pass on the [pytest workflow](https://github.com/liquidz00/Patcher/blob/main/.github/workflows/pytest.yml) before a PR can merge.
```

## Environment setup

Patcher uses [`uv`](https://github.com/astral-sh/uv) for dependency management and `ruff` for formatting and linting. The `Makefile` wraps the common workflows.

### One-time

After cloning your fork:

```{code-block} console
$ make dev
```

`make dev` creates a virtual environment if one doesn't exist, installs both the `patcherctl` and `patcher-api` workspace members with all optional extras (`dev`, `docs`, `test`), and is the canonical setup target for contributors. Re-run it after pulling changes that touch any `pyproject.toml`.

```{note}
The `Xcode Command Line Tools` are required for the `make` command on macOS.
```

### Vendor documentation submodules

Patcher pins read-only copies of the [Installomator](https://github.com/Installomator/Installomator) and [AutoPkg](https://github.com/autopkg/autopkg) wikis as git submodules under `vendor-docs/`. These exist as a reference for contributors and for Claude when reasoning about upstream behavior; they are not surfaced into the user-facing docs. Initialize them once after cloning:

```{code-block} console
$ make init-vendor-docs
```

Refresh against latest upstream when needed:

```{code-block} console
$ make update-vendor-docs
```

Working without them is fine — every Patcher build, test, and doc target runs without the submodules populated.

### Optional but recommended: pre-commit hooks

```{code-block} console
$ make pre-commit
$ make pre-commit-run
```

The first command installs Patcher's `pre-commit` hooks; the second runs them across the entire repo. Once installed, the hooks run automatically on every `git commit`. This catches ruff formatting drift, trailing whitespace, and other mechanical issues before they reach the PR.

## Makefile commands

The complete list of available targets, sourced from `make help`:

```{code-block} text
help                   Show this help message
venv                   Create virtual environment if missing
install                Install base dependencies (Patcher only)
dev                    Install everything for monorepo development (Patcher + API + all extras)
uninstall              Remove the .venv directory
clean                  Remove caches, build artifacts, and the .venv
lint                   Check code style with ruff
format                 Auto-format code with ruff
lock                   Update uv.lock
upgrade                Upgrade all dependencies to latest versions
test                   Run Patcher unit tests (excludes integration)
test-integration       Run Patcher integration tests only
smoke-test             Hand-run smoke check of PatcherClient against a live Jamf instance
test-api               Run Patcher API tests
serve-api              Run Patcher API locally with hot-reload
pre-commit             Install pre-commit hooks
pre-commit-run         Run pre-commit on all files
pre-commit-update      Update pre-commit hooks to latest versions
build                  Build distribution packages (sdist + wheel)
docs                   Build Sphinx documentation
init-vendor-docs       One-time after clone - pull submodule content
update-vendor-docs     Refresh vendor docs to latest upstream (Installomator/Autopkg Wikis)
```

Run `make help` from the repo root to see the live list. The Makefile is the source of truth; if this page drifts, the Makefile wins.

```{tip}
`make lint` before opening a PR catches the same checks CI runs. `make format` auto-fixes the mechanical ones. Neither is strictly required (pre-commit hooks and the GitHub runner enforce both), but running them locally is faster than waiting for CI to fail.
```

(integration_tests)=

## Integration tests

Patcher includes an opt-in integration test suite that exercises a real Jamf Pro API instance rather than mocked components. Integration tests live in `tests/integration/` and are marked with the `integration` pytest marker.

By default, `make test` **excludes** integration tests so the standard development loop stays fast and offline. Run them explicitly:

```{code-block} console
$ make test-integration
```

### What gets exercised

Integration tests use real {class}`~patcher.core.config_manager.ConfigManager`, {class}`~patcher.clients.token_manager.TokenManager`, and {class}`~patcher.clients.jamf.JamfClient` objects — no mocks at the HTTP boundary. This validates the full chain: credential loading, OAuth token flow, real HTTP calls, response parsing, and error handling against actual Jamf Pro responses.

Particularly useful when:

- Verifying that a refactor (e.g. the httpx transport migration) hasn't changed observable behavior.
- Reproducing a bug that only surfaces against real API responses.
- Smoke-testing before a release.

### Default target instance

By default, integration tests target Jamf's [publicly-published dummy instance](https://developer.jamf.com/jamf-pro/docs/populating-dummy-data) at `https://dummy.jamfcloud.com`. The credentials are public and intentionally shareable. No setup is required to run against this default.

```{note}
Jamf documents that the dummy instance data "is not comprehensive nor does it truly mirror a production Jamf Pro environment." Treat it as smoke-test coverage, not exhaustive validation. Tokens issued by the dummy instance are also short-lived, which is why `seconds_remaining > 0` is the test idiom for verifying token freshness rather than the stricter {attr}`~patcher.core.models.token.AccessToken.is_expired`.
```

### Pointing at your own test tenant

Set these environment variables before invoking the suite:

```{code-block} console
$ export PATCHER_INTEGRATION_URL="https://your-tenant.jamfcloud.com"
$ export PATCHER_INTEGRATION_CLIENT_ID="..."
$ export PATCHER_INTEGRATION_CLIENT_SECRET="..."
$ make test-integration
```

Each variable falls back independently. You can override just the URL while keeping the dummy credentials, for example.

### Not in CI

The integration suite does **not** run in the default GitHub Actions workflow. Hitting a shared dummy instance on every PR would be discourteous and slow CI considerably. Run integration tests locally before pushing significant changes, or trigger them through a manual workflow when needed.

## Next steps

If anything in this guide is unclear, reach out on the [#patcher channel](https://macadmins.slack.com/archives/C07EH1R7LB0) in [MacAdmins Slack](https://www.macadmins.org). The maintainers are active there.

If you're new to the GitHub PR flow, GitHub's [own documentation](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork) is the canonical walkthrough. The [Keep on Coding](https://www.youtube.com/watch?v=jRLGobWwA3Y) YouTube video is an option for visual learners.

```{toctree}
:hidden:

architecture
roadmap
```
