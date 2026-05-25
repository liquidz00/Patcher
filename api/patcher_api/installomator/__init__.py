"""
Installomator subsystem for the Patcher API.

Co-locates the three pieces that handle Installomator label data:

- :mod:`~patcher_api.installomator.parser` — turn a raw ``.sh`` label
  fragment into a dict of variable assignments (quote-aware scanner).
- :mod:`~patcher_api.installomator.resolver` — evaluate a label's
  shell-expression values into concrete strings in Python (no subprocess
  by default).
- :mod:`~patcher_api.installomator.ingest` — fetch the upstream label
  tree, gate on blob SHA, parse + resolve, and persist to the catalog.

The DB table lives in :mod:`patcher_api.models.installomator`; the
package/CLI-side client lives in ``patcher.clients.installomator``.
"""
