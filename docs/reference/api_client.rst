:html_theme.sidebar_secondary.remove: True

==========
API Client
==========

.. dropdown:: Summary
    :icon: archive

    The ``ApiClient`` is responsible for *most* API calls. Exceptions to this are any API calls interacting with AccessTokens, and calls made during the initial Setup.

.. autoclass:: patcher.client.api_client.ApiClient
    :members:
