"""
Upstream ingestion — pulls real catalog data from external sources.

Each submodule handles one upstream (Homebrew Cask, Installomator, etc.). The
``fetch_*`` functions hit the network; the ``ingest_*`` functions take already-
fetched data + a session, which keeps the storage logic unit-testable without
HTTP mocking.
"""
