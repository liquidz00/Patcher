.. _setup:

=====
Setup
=====

Our aim as developers of this tool is to streamline the setup and installation process to be as straightforward as possible. We understand there's nothing more frustrating than the anticipation of using a new tool, only to be bogged down by extensive configuration or setup steps before you can even start. To address this, we introduced a setup assistant in version ``1.3.2`` (and up) that automates the initial configuration. This page will demonstrate how the tool operates under the hood, giving you the end-user insight into how to trigger it again if necessary.

First Run Detection
-------------------

Patcher needs to know whether it is being run for the first time. This is important so that credentials are saved and stored properly and :ref:`user-interface customizations <customize_reports>` are setup for subsequent uses. Here is how the process works:

1. **First Run Check**: When Patcher is executed, it looks for a property list in Patcher's Application Support directory. Specifically, it checks for the presence of ``com.liquidzoo.patcher.plist`` in ``/Users/$username/Library/Application Support/Patcher``, where ``$username`` denotes the currently logged in user.

2. **Key Check**: If the property list is found, Patcher will parse its contents for the ``first_run_done`` key.

   - If the file does not exist, or if the key is set to ``False``, the setup assistant is triggered.
   - The key *must* be set to ``True`` to prevent the setup assistant from running.

API credential creation
-----------------------

Beginning with Patcher version 1.3.4, the Setup Assistant handled in the :mod:`~patcher.client.setup` class will prompt for a Jamf Pro username and password. The admin credentials are not stored permanently--they are **only** used for initial authentication for creating the API roles and client.

The setup assistant also has checks in place to account for the use of SSO. As the Jamf Pro API `does not support the use of SSO, <https://developer.jamf.com/jamf-pro/docs/jamf-pro-api-overview#authentication-and-authorization>`_ you may be prompted to verify your account is not configured with SSO. In the event it is, creating an :ref:`API Role and Client will have to be done manually <jamf-guide>`.

Storing Credentials
^^^^^^^^^^^^^^^^^^^

Patcher uses the ``keyring`` library to save credentials to the login keychain in macOS. In some situations, it may be easier or necessary to save the credentials before using Patcher. If you find this may apply to you, copy the code snippet below into your code editor of choice. If you do not have the ``keyring`` library already installed, it can be installed via ``pip``. After installing keyring, replace the placeholder values for ``api_url``, ``api_client_id``, and ``api_client_secret`` and run the script.

.. code-block:: python

    import keyring

    api_url = "Your Jamf URL here"  # https://anyorg.jamfcloud.com
    api_client_id = "Your client ID here"
    api_client_secret = "Your client secret here"

    keyring.set_password("Patcher", "URL", api_url)
    keyring.set_password("Patcher", "CLIENT_ID", api_client_id)
    keyring.set_password("Patcher", "CLIENT_SECRET", api_client_secret)

If the snippet runs without any errors, these credentials can be viewed in the Keychain Access application under the login keychain.

.. tip::

    Patcher is configured to handle generating bearer tokens and ensuring they are refreshed. Therefore, it is not required to generate a bearer token as part of this process.
