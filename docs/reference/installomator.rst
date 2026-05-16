=============
Installomator
=============

.. seealso::

    :ref:`Installomator Usage Docs <installomator>`

.. autoclass:: patcher.core.installomator.InstallomatorClient
    :members:

Shell-expression helpers
========================

Module-level helpers for working with parsed Installomator label values.
Public entry points for callers that want to evaluate or sanitize label
fields without going through the full :class:`InstallomatorClient` flow
(notably the Patcher API ingest and stitch layers, which exercise these
directly).

.. autofunction:: patcher.core.installomator.is_shell_expression

.. autofunction:: patcher.core.installomator.looks_like_clean_http_url
