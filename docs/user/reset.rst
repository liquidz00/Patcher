.. _resetting_patcher:

.. _reset:

======
Reset
======

The ``reset`` command restores specific configurations in Patcher, allowing users to reset **credentials, UI settings, or cached data**. By default, a **full reset** clears all configurations and triggers the setup process. Users can reset individual components without affecting other settings.

.. seealso::
    For more on resuming or forcing a fresh setup, see :ref:`Resumable Setup <starting_fresh>`. 
 
Parameters
----------

.. param:: kind
    :type: str
    :required:

    Specifies the type of reset to perform:

    .. container:: sd-table

        .. list-table::
            :header-rows: 1
            :widths: auto

            * - Option
              - Description
            * - ``full``
              - Resets credentials, UI elements, and property list file. Subsequently triggers :class:`~patcher.client.setup.Setup` to start setup
            * - ``UI``
              - Resets UI elements of PDF reports (header & footer text, custom font and optional logo)
            * - ``creds``
              - Resets credentials stored in Keychain. Useful for testing Patcher in a non-production environment first. Allows specifying which credential to reset using the ``--credential`` option
            * - ``cache``
              - Removes all cached data from the cache directory stored in ``~/Library/Caches/Patcher``
    
    .. note::
        Options are not case-sensitive and are converted to lowercase automatically at runtime

.. param:: credential
    :type: Optional[str]

    The specific credential to reset when performing credentials reset. Defaults to all credentials if none specified.

Usage
-----

.. important::

    Performing a full credential reset will prompt for **all client credentials** (URL, Client ID, Client Secret).
    **Do not use this method** unless you are confident you have access to these credentials, especially if:

    - Your environment does **not** use SSO.
    - You relied on the automatic setup of Patcher (:attr:`~patcher.client.setup.SetupType.STANDARD`)

.. note::

    You can reset individual credentials by specifying one of the following options:

    - ``url``
    - ``client_id``
    - ``client_secret``

.. _full_reset:

.. tab-set::
    
    .. tab-item:: All (Full)

        .. code-block:: console

            $ patcherctl reset full

        This will reset all configurations (credentials, UI elements, and property list file) and initiate the setup process.

    .. tab-item:: UI

        .. code-block:: console

            $ patcherctl reset UI

        This is useful if you only need to refresh the appearance of generated reports (header/footer text or custom logos).

    .. tab-item:: Credentials

        .. code-block:: console

            $ patcherctl reset creds

        This will prompt you to provide new values for URL, Client ID, and Client Secret.

    .. tab-item:: Specific Credential

        .. code-block:: console

            $ patcherctl reset creds --credential url

        You will be prompted to enter a new value for the credential specified to be reset.

    .. tab-item:: Cached data

        .. code-block:: console

            $ patcherctl reset cache

        Removes all cache files from cache directory. See :ref:`data caching <caching>` for more.
