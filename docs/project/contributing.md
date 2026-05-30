---
description: "Contribute to Patcher: bug reports, feature requests, PR workflow, environment setup with uv, Makefile targets, and integration tests."
---

(contributing_index)=

# Contributing

:::{rst-class} lead
Contributions are welcome and don't require writing Python.
:::

---

We firmly believe that diverse backgrounds strengthen a product. Share your ideas regardless of your programming experience, half the time the most valuable contribution is naming a problem clearly.

```{important}
The MacAdmin community is full of people who quietly believe they're the only one who doesn't actually know what they're doing. If you've ever second-guessed whether you should create an issue or reach out, or ever thought "it's not worth it", **consider this an invitation to send the next one**. Seriously. Reports of all types and all experiences are not only welcomed but genuinely encouraged.
```

## How to contribute

The shortest path is to **get in touch first**. Open a [bug report](https://github.com/liquidz00/Patcher/issues/new?template=bug_report.yml), [feature request](https://github.com/liquidz00/Patcher/issues/new?template=feature_request.yml), or [feedback issue](https://github.com/liquidz00/Patcher/issues/new?template=feedback.yml) describing what you want to change before writing code. This avoids the "you already shipped the same thing in a branch" problem and lets us scope the change together.

### Pull request workflow

We do our best to follow the standard [GitHub flow](https://docs.github.com/en/get-started/using-github/github-flow):

::::::{steps}

:::::{step} [Fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo) the Patcher repository.

:::::

:::::{step} Clone your fork locally.
::::{tab-set}

:::{tab-item} git
```bash
$ git clone https://github.com/liquidz00/Patcher.git /clone/destination/here
```
:::

:::{tab-item} gh
```bash
$ gh repo clone liquidz00/Patcher /clone/destination/here
```
:::
::::
:::::

:::::{step} Branch off develop with a descriptive name.
```bash
$ git checkout develop
$ git checkout -b <fix|feat|perf|security>/your-description-here
```
:::::

:::::{step} Pull in latest changes before submitting a PR.
```bash
$ git fetch origin develop && git pull
```
:::::

:::::{step} Open the PR against the develop branch.
```{note}
PRs go to the `develop` branch, not `main`. The `main` branch tracks stable releases; ongoing development lands on `develop` and is merged to `main` as part of the release cut. Tests must pass on the [pytest workflow](https://github.com/liquidz00/Patcher/blob/main/.github/workflows/pytest.yml) before a PR can merge.
```
:::::

::::::


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

(testing)=

## Testing

Three suites, each shaped for a different feedback loop. Together they cover what changes between commits, what changes when Jamf changes, and what changes when the catalog ingest changes.

```{mermaid}
%%{init: {'theme':'base', 'themeVariables': {'fontSize': '14px'}}}%%
flowchart LR
  Dev([Developer])
  Unit[Unit<br/>tests/]
  API[API<br/>api/tests/]
  Integration[Integration<br/>tests/integration/]
  Live[(dummy.jamfcloud.com)]
  CI{{Every PR}}
  Merge([Merge])

  Dev --> Unit
  Dev --> API
  Dev -. opt-in .-> Integration
  Integration -. real HTTP .-> Live
  Unit --> CI
  API --> CI
  CI --> Merge
```

### Why three suites

**Unit tests** (`tests/`, excluding `tests/integration/`) mock the HTTP and filesystem boundaries. They run on every PR and finish fast because the boundary is the contract that matters: when Jamf's API contract is stable, the unit suite is enough to catch regressions in our parsing, matching, and report-building code. This is the suite that turns red when you break refactor work.

**API tests** (`api/tests/`) cover the catalog service itself: ingest from upstream sources, stitch logic, FastAPI routes, ETag behavior. They're separate from the package tests because the API can ship independently, but they run alongside the unit suite on every PR (`make test-api` is the second step in the [pytest workflow](https://github.com/liquidz00/Patcher/blob/main/.github/workflows/pytest.yml)).

**Integration tests** (`tests/integration/`) hit Jamf's public [dummy instance](https://developer.jamf.com/jamf-pro/docs/populating-dummy-data) with no mocks at the HTTP boundary. They validate the full chain — credential loading, OAuth token flow, real HTTP, response parsing — against actual Jamf Pro responses. They are **not** in CI because hitting a shared dummy on every PR would be discourteous and slow. Run them locally before pushing anything that touches request shaping or response parsing: `make test-integration`.

The [pytest workflow](https://github.com/liquidz00/Patcher/blob/main/.github/workflows/pytest.yml) badge on the [landing page](../index.md) is the live signal for unit + API. Click it for the latest run.

(integration_tests)=

### Integration: configuration

By default, integration tests target the Jamf dummy instance with public credentials, so no setup is needed. To point at your own test tenant:

```{code-block} console
$ export PATCHER_INTEGRATION_URL="https://your-tenant.jamfcloud.com"
$ export PATCHER_INTEGRATION_CLIENT_ID="..."
$ export PATCHER_INTEGRATION_CLIENT_SECRET="..."
$ make test-integration
```

Each variable falls back independently. Override just the URL while keeping the dummy credentials if you want.

```{note}
Jamf documents that the dummy instance data "is not comprehensive nor does it truly mirror a production Jamf Pro environment." Treat it as smoke-test coverage, not exhaustive validation. Tokens issued by the dummy instance are also short-lived, which is why `seconds_remaining > 0` is the integration-suite idiom for verifying token freshness rather than the stricter {attr}`~patcher.core.models.token.AccessToken.is_expired`.
```

## Next steps

If anything in this guide is unclear, reach out on the [#patcher channel](https://macadmins.slack.com/archives/C07EH1R7LB0) in [MacAdmins Slack](https://www.macadmins.org). The maintainers are active there.

If you're new to the GitHub PR flow, GitHub's [own documentation](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork) is the canonical walkthrough. The [Keep on Coding](https://www.youtube.com/watch?v=jRLGobWwA3Y) YouTube video is an option for visual learners.
