.. _setup:

===============
Setup Assistant
===============

Our aim as developers of this tool is to streamline the setup and installation process to be as straightforward as possible. We understand there's nothing more frustrating than the anticipation of using a new tool, only to be bogged down by extensive configuration or setup steps before you can even start. To address this, we introduced a setup assistant in version ``1.3.2`` (and up) that automates the initial configuration. This page will demonstrate how the tool operates under the hood, giving you the end-user insight into how to trigger it again if necessary.

First Run Detection
-------------------

When you first launch Patcher, the ``com.liquidzoo.patcher.plist`` file in the Application Support directory (``$HOME/Library/Application Support/Patcher``) is created. This file serves as the main configuration storage, ensuring that Patcher retains necessary settings between runs.

To determine whether the setup assistant should be triggered, Patcher checks whether it is being run for the first time. This is important so that credentials are saved and stored properly and :ref:`user-interface customizations <customize_reports>` are set up for subsequent uses. Here is how the process works:

1. **First Run Check**: When Patcher is executed, it looks for the property list file. Specifically, it checks for the presence of ``com.liquidzoo.patcher.plist`` in ``/Users/$username/Library/Application Support/Patcher``, where ``$username`` denotes the currently logged in user.

2. **Key Check**: If the property list is found, Patcher will parse its contents for the ``setup_completed`` key.

   - If the file does not exist, or if the key is set to ``False``, the setup assistant is triggered.
   - The key *must* be set to ``True`` to prevent the setup assistant from running.

Configuration Persistence
-------------------------

Once setup is completed successfully, the ``setup_completed`` key will automatically be set to ``True``:

.. code-block:: xml

    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>Setup</key>
        <dict>
            <key>first_run_done</key>
            <true/>
        </dict>
    </dict>
    </plist>

.. admonition:: Warning
    :class: warning

    **Do not modify** the ``setup_completed`` key directly. Altering this key may lead to unexpected behavior. If you need to reset the initial setup state, use the ``--reset`` command instead. For more information, see :ref:`resetting Patcher <resetting_patcher>`.

.. _setup_type:

Choosing Setup type
--------------------

The setup assistant will show a greeting message and then prompt you which setup method to proceed with:

.. code-block:: console

    Thanks for downloading Patcher!

    [...]  # Rest of greeting

    Choose setup method (1: Standard setup, 2: SSO setup) [1]:

Which Method to Use
^^^^^^^^^^^^^^^^^^^

- **Select SSO** if you use Single Sign On (SSO) to sign into Jamf. This is due to the Jamf Pro API `not supporting the use of SSO <https://developer.jamf.com/jamf-pro/docs/jamf-pro-api-overview#authentication-and-authorization>`_ for authorization. Both an API role and API client will need to be created manually to pass credentials to the setup assistant. See :ref:`the Jamf Deployment Guide <api-creation>` for instructions on completing this. 
- **Select Standard** if you'd like Patcher to automatically create an API Role & Client on your behalf. You will be prompted for your username and password during setup, but **these values are never stored permanently by Patcher**. They are *solely* used to obtain a basic token to create the API integration as expected. 


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
