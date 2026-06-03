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

```{note}
The MacAdmin community is full of people who quietly believe they're the only one who doesn't actually know what they're doing. If you've ever second-guessed whether you should create an issue or reach out, or ever thought "it's not worth it", **consider this an invitation to send the next one**. Seriously. Reports of all types and all experiences are not only welcomed but genuinely encouraged.
```

## How to Contribute

The shortest path is to **get in touch first**. Open a [bug report](https://github.com/liquidz00/Patcher/issues/new?template=bug_report.yml), [feature request](https://github.com/liquidz00/Patcher/issues/new?template=feature_request.yml), or [feedback issue](https://github.com/liquidz00/Patcher/issues/new?template=feedback.yml) describing what you want to change before writing code. This avoids the "you already shipped the same thing in a branch" problem and lets us scope the change together.

### Pull Request Workflow

We do our best to follow the standard [GitHub flow](https://docs.github.com/en/get-started/using-github/github-flow):

::::::{steps}

:::::{step} [Fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo) the Patcher repository.

:::::

:::::{step} Clone your fork locally.
::::{tab-set}

:::{tab-item} {iconify}`devicon:git` git
```bash
$ git clone https://github.com/liquidz00/Patcher.git
```
:::

:::{tab-item} {iconify}`octicon:mark-github-16` gh
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
```{admonition} Important
:class: caution

PRs go to the `develop` branch, not `main`. The `main` branch tracks stable releases, ongoing development lands on `develop` and is merged to `main` as part of the release cut. Tests must pass on the [pytest workflow](https://github.com/liquidz00/Patcher/blob/main/.github/workflows/pytest.yml) before a PR can merge.
```
:::::

::::::


## Environment Setup

Patcher uses [`uv`](https://github.com/astral-sh/uv) for dependency management and [`ruff`](https://docs.astral.sh/ruff/) for formatting and linting. The `Makefile` wraps the common workflows.

```{code-block} bash
:caption: Execute after cloning your fork
$ make dev
```

`make dev` creates a virtual environment if one doesn't exist, installs both the `patcherctl` and `patcher-api` workspace members with all optional extras (`dev`, `docs`, `test`), and is the canonical setup target for contributors. Re-run it after pulling changes that touch any `pyproject.toml`.

```{note}
The `Xcode Command Line Tools` are required for the `make` command on macOS.
```

### Vendor Documentation Submodules

Patcher pins read-only copies of the [Installomator](https://github.com/Installomator/Installomator) and [AutoPkg](https://github.com/autopkg/autopkg) wikis as git submodules under `vendor-docs/`. These exist as a reference for contributors and for Claude when reasoning about upstream behavior and are **not** surfaced into the user-facing docs.

```{code-block} bash
:caption: Initialize vendor docs

$ make init-vendor-docs
```

```{code-block} bash
:caption: Refresh against latest upstream when needed

$ make update-vendor-docs
```

These are completely optional, working without them is totally fine. Every Patcher build, test, and doc target runs without the submodules populated.

### Optional but Recommended: pre-commit Hooks

```{code-block} bash
:caption: Install pre-commit hooks

$ make pre-commit
```

```{code-block} bash
:caption: Run pre-commit on all files

$ make pre-commit-run
```

Once installed, the hooks run automatically on every `git commit`. This catches ruff formatting drift, trailing whitespace, and other mechanical issues before they reach the PR.

## Makefile Commands

```{code-block} text
:caption: The complete list of available targets, sourced from `make help`

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

### Why Three Suites

**Unit tests** (`tests/`, excluding `tests/integration/`) mock the HTTP and filesystem boundaries. They run on every PR and finish fast because the boundary is the contract that matters: when Jamf's API contract is stable, the unit suite is enough to catch regressions in our parsing, matching, and report-building code. This is the suite that turns red when you break refactor work.

**API tests** (`api/tests/`) cover the catalog service itself. Ingest from upstream sources, stitch logic, FastAPI routes, and ETag behavior. They're separate from the package tests because the API can ship independently, but they run alongside the unit suite on every PR.

(integration_tests)=

**Integration tests** (`tests/integration/`) hit Jamf's public [dummy instance](https://developer.jamf.com/jamf-pro/docs/populating-dummy-data) with no mocks at the HTTP boundary. They validate the full chain — credential loading, token flow, real HTTP, response parsing — against actual Jamf Pro responses. They are **not** in CI because hitting a shared dummy on every PR is just plain rude. Run `make test-integration` locally before pushing anything that touches request shaping or response parsing.

The [pytest workflow](https://github.com/liquidz00/Patcher/blob/main/.github/workflows/pytest.yml) badge on the [landing page](../index.md) is the live signal for unit and API tests. Click it for the latest run.

:::{note}
Treat integration tests to the dummy instance as smoke-test coverage, not exhaustive validation. Configure environment variables if you would like to leverage your own Jamf pro tenant for integration tests.

```{code-block} bash
:caption: Pointing integration tests at your own test tenant

$ export PATCHER_INTEGRATION_URL="https://your-tenant.jamfcloud.com"
$ export PATCHER_INTEGRATION_CLIENT_ID="..."
$ export PATCHER_INTEGRATION_CLIENT_SECRET="..."
$ make test-integration
```
:::

## Next Steps

If anything in this guide is unclear, reach out on the [#patcher channel](https://macadmins.slack.com/archives/C07EH1R7LB0) in [MacAdmins Slack](https://www.macadmins.org). The maintainers are active there.

If you're new to the GitHub PR flow, GitHub's [own documentation](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork) is the canonical walkthrough. The [Keep on Coding](https://www.youtube.com/watch?v=jRLGobWwA3Y) YouTube video is an option for visual learners.
