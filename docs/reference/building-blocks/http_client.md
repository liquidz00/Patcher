(http_client)=

# HTTPClient

```{eval-rst}
.. autoclass:: patcher.clients.HTTPClient
   :members:
   :private-members: _raise_for_status, _request
```

Subclasses use ``_request`` to share the per-instance semaphore and the
``httpx.RequestError → APIResponseError`` translation; ``PatcherAPIClient._get``
and ``_post`` route through it.
