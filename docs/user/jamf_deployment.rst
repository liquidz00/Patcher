.. _jamf-guide:

=====================
Jamf Deployment Guide
=====================

This guide covers setting up an API Role & Client in Jamf Pro, managing access tokens, and adding patch management/software titles to your Jamf Pro instance.

.. important::
    Patcher (v1.3.4+) can now automatically create API Roles and Clients on your behalf. The setup assistant will prompt for your Jamf Pro admin credentials **only** to create the necessary components, Patcher does not and will not store them permanently whatsoever. If your organization uses Single-Sign-On (SSO) to login to Jamf, **then you will need to create an API Role & Client** as the Jamf API `does not support SSO <https://developer.jamf.com/jamf-pro/docs/jamf-pro-api-overview#authentication-and-authorization>`_.

Creating an API Role & Client
=============================

To utilize Patcher with Jamf Pro, you need to create an API Role and Client first. Reference the `Jamf Pro Documentation <https://learn.jamf.com/bundle/jamf-pro-documentation-current/page/API_Roles_and_Clients.html>`_ or follow the steps below.

API Role & Privileges
---------------------

Before creating an API client, you must establish an API role with the necessary privileges:

1. Navigate to **Settings** in the Jamf Pro sidebar.
2. Under **System**, select **API Roles and Clients**.
3. Switch to the **API Roles** tab.
4. Click **New** to create a new role.
5. Provide a meaningful display name for the API role (e.g., "Patch Reports Access").
6. In the **Jamf Pro API Role privileges** field, type the following privileges required for use with Patcher

   * Read Patch Management Software Titles
   * Read Patch Policies
   * Read Mobile Devices
   * Read Mobile Device Inventory Collection
   * Read Mobile Device Applications
   * Read API Integrations
   * Read API Roles
   * Read Patch Management Settings

7. Click **Save** to create the role.

API Client
----------

Once your API role is ready, proceed to create an API client:

1. Follow steps 1-2 from above to navigate back to the **API Roles and Clients** section if not already there.
2. Click on the **API Clients** tab.
3. Select **New** to initiate a new API client creation.
4. Assign a clear and descriptive display name for the API client (e.g., "Patcher Client").
5. In the **API Roles** field, assign the previously created API role to this client.
6. Define the **Access Token Lifetime**. This defines how long each token remains valid. See `Access Token Lifetime`_ below for more information.
7. Enable the API client by clicking **Enable API Client**.
8. Click **Save**.
9. Record the **Client ID** value for safe-keeping.

Generating a Client Secret
--------------------------

.. important::

   Record the generated client secret immediately and securely; it is shown **only once** and is essential for your authenticating API calls.

1. Within Jamf Pro, go to the previously created API client's details page.
2. Click **Generate Client Secret** to create a new secret.
3. Confirm the action in the dialog box by selecting **Create Secret**.
4. The client secret will now be displayed.

Access Token Lifetime
=====================

When defining the access token lifetime, it is recommended to use a duration of at least 5 minutes. Patcher is designed to handle automatic token refreshing and generation. Longer durations reduce the frequency of token regeneration, thereby decreasing administrative overhead. However, ensure that the chosen duration aligns with your organization's security policies.

Token Generation
----------------

In situations where AccessTokens need to be generated manually, copy the bash script below into the code editor of your choice. Substitute your Jamf Pro URL in the ``url`` variable, and modify the ``client_id`` and ``client_secret`` values with the Client ID and secret generated from the steps above.

.. dropdown:: Additional Reference

    For more details, reference the `Client Credentials Authorization Recipe <https://developer.jamf.com/jamf-pro/recipes/client-credentials-authorization>`_ Jamf Developer documentation.

.. code-block:: bash

   #!/bin/bash

   url="https://yourserver.jamfcloud.com"
   client_id="your-jamf-api-client-id"
   client_secret="your-jamf-api-client-secret"

   response=$(curl --silent --location --request POST "${url}/api/oauth/token" \
     --header "Content-Type: application/x-www-form-urlencoded" \
     --data-urlencode "client_id=${client_id}" \
     --data-urlencode "grant_type=client_credentials" \
     --data-urlencode "client_secret=${client_secret}")
   token=$(echo "$response" | plutil -extract access_token raw -)
   echo "$token"

You can now pass the Client ID, Client Secret, and Token values when prompted by the setup assistant. The Jamf URL, client ID, client secret, and access token are all saved to keychain and can be modified if necessary.

Adding Patch Management/Software Titles
=======================================

When utilizing the Patcher tool with Jamf Pro, it's crucial to understand that the tool exclusively pulls data from configured patch management titles. As it relies on the Jamf Pro API, patch data of software titles not available in the `Patch Management Software Titles <https://learn.jamf.com/en-US/bundle/jamf-app-catalog/page/Patch_Management_Software_Titles.html>`_ list in Jamf App Catalog or Title Editor will not be exported. Therefore, ensure that all necessary software titles are properly configured within Jamf Pro to ensure accurate and comprehensive patch management.

Refer to `Configuring a Patch Management Software Title <https://learn.jamf.com/en-US/bundle/jamf-pro-documentation-current/page/Configuring_a_Patch_Management_Software_Title.html>`_ in the Jamf Pro Documentation for instructions on setting up software titles for patch management purposes.
