.. _contributing_index:

Contributing
============

Contributions to Patcher are encouraged and welcomed. Contributing does not *have* to mean writing Python code! Project documentation can always be improved and `feature requests <https://github.com/liquidz00/Patcher/issues/new?assignees=&labels=enhancement&projects=&template=feature_request.md&title=%5BFEATURE%5D+Your+feature+request+title>`_ can be submitted for new ideas or functionality. We, the developers of this tool, **firmly believe** that diverse backgrounds strengthen a product. Therefore, we encourage you to share your ideas and thoughts, regardless of your programming experience.

How to Contribute
-----------------

First and foremost, get in touch! Ideally, this would be done by submitting a feature request (for introducing new functionality) or an issue if something is not working as expected. Although this is not required, it is *greatly appreciated*.

Pull Requests
^^^^^^^^^^^^^

We recommend following the typical `GitHub workflow <https://docs.github.com/en/get-started/using-github/github-flow>`_:

- `Fork <https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo>`_ the Patcher repository
- Clone the repository locally in the directory of your choosing
- Create a feature branch that roughly describes the changes implemented (i.e., ``kandji`` if introducing functionality with Kandji)
- Work through code review

.. important::

    Be sure to pull any changes from the ``main`` branch before submitting a pull request.

All pull requests should be made against the ``main`` branch of the repository. The pull request will be reviewed by project maintainers, and must pass the pytest unit tests before it is merged. Unit tests can be found in the `tests <https://github.com/liquidz00/Patcher/tree/main/tests>`_ directory in the repository. Tests are triggered automatically by a GitHub action which can be found in the `pytest.yml <https://github.com/liquidz00/Patcher/blob/main/.github/workflows/pytest.yml>`_ file.

Environment Setup
-----------------

Patcher uses ``ruff`` for both formatting and linting before any changes are merged to ``main``. The ``Makefile`` automates the lint + format invocations. Configuration for ``ruff`` lives in the `pyproject.toml <https://github.com/liquidz00/Patcher/blob/main/pyproject.toml>`_ file under ``[tool.ruff]``.

Virtual Environment
^^^^^^^^^^^^^^^^^^^

After forking the repository, create and activate a virtual environment with the following command:

.. code-block:: console

    $ python3 -m venv venv && source venv/bin/activate

.. dropdown:: Virtual Environment Reference
    :color: info
    :icon: code

    For more information on creating virtual environments, reference `the python packaging guide <https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/#create-and-use-virtual-environments>`_

Makefile commands
^^^^^^^^^^^^^^^^^

.. note::

    Be sure to install the ``Xcode Command Line Tools`` in order to use the ``make`` command.

With the virtual environment (``venv``) activated, execute the command ``make install``. This will ensure all project dependencies (including development dependencies) are installed properly.

Other command options available are:

``install``
    Installs ``patcherctl``'s base runtime dependencies into the active venv. Use ``dev`` (below) for typical development work.

``dev``
    Sets up the full monorepo development environment — installs both ``patcherctl`` and ``patcher-api`` workspace members along with all optional extras (``dev``, ``docs``, ``test``). This is the recommended target for contributors.

``uninstall``
    Removes the ``.venv`` directory entirely.

.. warning::

    ``make uninstall`` deletes the local virtual environment. Make sure no other tooling is relying on it before running this.

``clean``
    Removes caches (``__pycache__``, ``.pytest_cache``, ``.ruff_cache``), build artifacts (``build/``, ``dist/``, ``*.egg-info/``), coverage output (``.coverage``, ``htmlcov/``, ``coverage/``), the Sphinx docs build output (``docs/_build/``), and the ``.venv`` directory. Useful when starting from a clean slate.

``test``
    Runs the ``patcherctl`` unit tests using ``pytest``. **Integration tests are excluded** by default — see :ref:`integration_tests` below. Coverage runs automatically (configured in ``pyproject.toml`` under ``[tool.pytest.ini_options].addopts``); HTML coverage lands in ``coverage/htmlcov/``.

``test-api``
    Runs the ``patcher-api`` test suite. The API has its own ``pyproject.toml`` with separate pytest config; this target ``cd``-s into ``api/`` and runs pytest there.

``test-integration``
    Runs the integration test suite against a real Jamf Pro instance. See :ref:`integration_tests` below for details and credential overrides.

``serve-api``
    Runs the Patcher API locally with auto-reload via ``uvicorn``. Useful for hand-testing API changes against a real running service.

``lint``
    Runs ``ruff format --check`` and ``ruff check`` across the repo. Source of truth for code-style enforcement.

``format``
    Auto-formats with ``ruff format`` and applies ``ruff check --fix``. Does NOT remove unused imports — use ``lint`` for that.

``docs``
    Builds the Sphinx documentation into ``docs/_build/``.

``lock``
    Regenerates ``uv.lock`` based on current dependency declarations. Run after editing any ``pyproject.toml``.

``upgrade``
    Upgrades all dependencies to their latest versions (within version-pin constraints) and re-syncs the venv. Equivalent to ``uv lock --upgrade`` followed by ``make dev``.

``pre-commit``, ``pre-commit-run``, ``pre-commit-update``
    Install pre-commit hooks, run them across all files, or update hook revisions to latest, respectively.

``init-vendor-docs``, ``update-vendor-docs``
    Initialize or refresh the upstream wiki submodules under ``vendor-docs/`` (Installomator + AutoPkg). Run ``init-vendor-docs`` once after cloning if you didn't use ``--recursive``; run ``update-vendor-docs`` to bump submodules to upstream's latest state.

``build``
    Builds distribution packages (``sdist`` + ``wheel``) for ``patcherctl`` via ``uv build``.

.. tip::

    It's not required to run ``make format`` before pushing — pre-commit hooks (and the GitHub runner) catch formatting issues. But it's good hygiene to run ``make lint`` before opening a PR.

.. _integration_tests:

Integration Tests
-----------------

Patcher includes an opt-in integration test suite that exercises a real Jamf Pro API instance instead of mocked components. Integration tests live in ``tests/integration/`` and are marked with the ``integration`` pytest marker.

By default, ``make test`` **excludes** integration tests so the standard development loop stays fast and offline. Run them explicitly via:

.. code-block:: console

    $ make test-integration

What gets exercised
^^^^^^^^^^^^^^^^^^^

Integration tests use real :class:`~patcher.core.config_manager.ConfigManager`, :class:`~patcher.client.token_manager.TokenManager`, and :class:`~patcher.client.jamf.JamfClient` objects — no mocks at the HTTP boundary. This validates the full chain: credential loading, OAuth token flow, real HTTP calls, response parsing, and error handling against actual Jamf Pro responses.

This is particularly useful when:

- Verifying that a refactor (e.g. the httpx transport migration) hasn't changed observable behavior
- Reproducing a bug that only surfaces against real API responses
- Smoke-testing before a release

Default target instance
^^^^^^^^^^^^^^^^^^^^^^^

By default, integration tests target Jamf's `publicly-published dummy instance <https://developer.jamf.com/jamf-pro/docs/populating-dummy-data>`_ at ``https://dummy.jamfcloud.com``. The credentials are public and intentionally shareable. No setup is required to run the suite against this default.

.. note::

    Jamf documents that the dummy instance data "is not comprehensive nor does it truly mirror a production Jamf Pro environment." Treat it as smoke-test coverage, not exhaustive validation. Tokens issued by the dummy instance are also short-lived, which is why ``seconds_remaining > 0`` is the test idiom for verifying token freshness rather than the more strict :attr:`~patcher.core.models.token.AccessToken.is_expired`.

Pointing at your own test tenant
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To run the suite against your own Jamf Pro tenant (e.g. a Jamf Technology Partner test instance), set these environment variables before invoking the suite:

.. code-block:: console

    $ export PATCHER_INTEGRATION_URL="https://your-tenant.jamfcloud.com"
    $ export PATCHER_INTEGRATION_CLIENT_ID="..."
    $ export PATCHER_INTEGRATION_CLIENT_SECRET="..."
    $ make test-integration

Each environment variable falls back independently — you can override just the URL while keeping the dummy credentials, for example.

Not in CI
^^^^^^^^^

The integration suite does **not** run in the default GitHub Actions workflow. Hitting a shared dummy instance on every PR would be discourteous and slow CI considerably. Run integration tests locally before pushing significant changes, or trigger them through a manual workflow when wanted.

Next Steps
----------

If you have any questions about the process of Contributing, you are welcome to reach out. We are both fairly active on the `MacAdmins Slack <https://www.macadmins.org>`_.

Additionally, if you are not familiar with the process of pull requests, `GitHub provides documentation <https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork>`_ on the topic. For visual learners, the YouTube channel `Keep on Coding <https://www.youtube.com/watch?v=jRLGobWwA3Y>`_ provides an excellent demonstration video.
