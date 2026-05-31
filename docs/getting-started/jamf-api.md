---
description: "Create the Jamf Pro API role and client Patcher needs. Step-by-step setup for standard accounts and SSO-protected Jamf instances."
---

# Jamf Configuration

:::{rst-class} lead
Integrating Patcher with your Jamf instance.
:::

---

In order for Patcher to operate as expected a few things need to be setup on the Jamf side beforehand.

::::{highlights}
{iconify}`octicon:check-circle-fill-16` Software titles
: Configured for the apps you want to track.

{iconify}`octicon:check-circle-fill-16` API role
: Created with the correct privileges.

{iconify}`octicon:check-circle-fill-16` API client
: A client ID and client secret that Patcher uses to authenticate.
::::

This page walks through each. If your Jamf instance uses SSO, see [SSO considerations](#sso-considerations) below for extra steps you'll need to follow.

## Patch management software titles

Patcher only pulls data from **configured patch management titles**. A title can be available in the [catalog](https://learn.jamf.com/en-US/bundle/jamf-app-catalog/page/Patch_Management_Software_Titles.html) and still be invisible to Patcher. It won't show up in reports until you've configured it for your instance.

:::{seealso}
[Configuring a Patch Management Software Title](https://learn.jamf.com/en-US/bundle/jamf-pro-documentation-current/page/Configuring_a_Patch_Management_Software_Title.html) (Jamf Pro Documentation).
:::

## Create an API role

::::{steps}

:::{step} In Jamf Pro, go to **Settings**.
:::

:::{step} Under **System**, select **API Roles and Clients**.
:::

:::{step} Switch to the **API Roles** tab and click **New**.
:::

:::{step} Give the role a meaningful display name (e.g. `Patcher-Roles`).
:::

:::{step} Under **Jamf Pro API Role privileges**, add the following:
- Read Patch Management Software Titles
- Read Patch Policies
- Read Mobile Devices
- Read Mobile Device Inventory Collection
- Read Mobile Device Applications
- Read API Integrations
- Read API Roles
- Read Patch Management Settings
- Update API Integrations
:::

:::{step} Click **Save**.
:::
::::

## Create an API client

Once your API role is ready, proceed to create an API client:

::::{steps}

:::{step} Follow steps 1-2 from above to navigate back to the **API Roles and Clients** section if not already there.
:::

:::{step} Click on the **API Clients** tab.
:::

:::{step} Select **New** to initiate a new API client creation.
:::

:::{step} Assign a clear and descriptive display name for the API client (e.g., "Patcher-Client").
:::

:::{step} In the **API Roles** field, assign the previously created API role to this client.
:::

:::{step} Define the **Access Token Lifetime**.
This defines how long each token remains valid. See [Token lifetime](#token-lifetime) below for more information.
:::

:::{step} Enable the API client by clicking **Enable API Client**.
:::

:::{step} Click **Save**.
:::

:::{step} Click Record the **Client ID** value for safe-keeping.
:::

::::

### Generate a client secret

:::{important}
Record the generated client secret immediately and securely as it is shown **only once**.
:::

::::{steps}

:::{step} Open the API client's details page.
:::

:::{step} Click **Generate Client Secret**.
:::

:::{step} Confirm by selecting **Create Secret**.
:::

:::{step} Copy the secret. You'll pass this to Patcher alongside the client ID.
:::

::::

You now have everything Patcher needs: a **Jamf URL**, a **Client ID**, and a **Client Secret**. On macOS, Patcher stores them in your login Keychain on first run and refreshes the OAuth token automatically as needed. On Linux and Windows there is no usable Keychain backend, so Patcher installs a no-op `keyring` backend at import time; library callers on those platforms construct `PatcherClient` with credentials in memory instead (`client_id=...`, `client_secret=...`, `server=...`) rather than relying on disk persistence.

## Token lifetime

:::{note}
You don't need to generate access tokens yourself. Patcher's {class}`~patcher.clients.token_manager.TokenManager` handles obtaining and refreshing tokens automatically.
:::

When configuring the API client's access token lifetime, **at least 5 minutes** is recommended. Longer durations reduce regeneration frequency and administrative overhead, but should align with your organization's security policies.

### Generate a token manually (optional)

In situations where AccessTokens *need* to be generated manually, copy the bash script below into the code editor of your choice. Substitute your Jamf Pro URL in the `url` variable, and modify the `client_id` and `client_secret` values with the Client ID and secret generated from the steps above.

:::::{tab-set}

::::{tab-item} {iconify}`mdi:bash` Bash
:sync: bash

```bash
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
expires_in=$(echo "$response" | plutil -extract expires_in raw -)

security add-generic-password -a "TOKEN" -s "Patcher" -w "$token" -U
security add-generic-password -a "TOKEN_EXPIRATION" -s "Patcher" -w "$expires_in" -U
```

::::

::::{tab-item} {iconify}`material-icon-theme:python` Python
:sync: python

:::{code-block} python
:caption: Requires `httpx` and `keyring`. Both are already installed with `patcherctl`.
import httpx
import keyring

url = "https://yourserver.jamfcloud.com/api/oauth/token"
client_id = "your-jamf-api-client-id"
client_secret = "your-jamf-api-client-secret"

response = httpx.post(
    url,
    data={
        "client_id": client_id,
        "grant_type": "client_credentials",
        "client_secret": client_secret,
    },
)
response.raise_for_status()

data = response.json()
keyring.set_password("Patcher", "TOKEN", data["access_token"])
keyring.set_password("Patcher", "TOKEN_EXPIRATION", str(data["expires_in"]))
:::

::::
:::::

(handling-sso)=

## SSO considerations

Patcher's [setup wizard](setup.md) can create the API role and client for you automatically, but only if your Jamf Pro account [doesn't use SSO](https://developer.jamf.com/jamf-pro/docs/jamf-pro-api-overview#authentication-and-authorization). If SSO is in play, you have two options:

### Option 1: Create the role and client manually

Follow the steps above to create the API role, client, and secret yourself. Then provide the Client ID and Client Secret to Patcher's setup wizard when prompted. This is the recommended path for SSO environments.

### Option 2: Temporary standard account

::::{steps}

:::{step} Temporarily [create a standard Jamf Pro user account](https://learn.jamf.com/en-US/bundle/jamf-pro-documentation-current/page/Jamf_Pro_User_Accounts_and_Groups.html#ariaid-title3:~:text=Click%20Save%20.-,Creating%20a%20Jamf%20Pro%20User%20Account,-Requirements) with administrator privileges.
:::

:::{step} Pass that account's credentials to Patcher's setup wizard. Patcher will create the API role and client on your behalf.
:::

:::{step} After setup completes, delete the temporary account.
:::

::::

## Multi-instance support

Patcher can be reset and pointed at a different Jamf URL via `patcherctl reset creds` (or by constructing {class}`~patcher.core.patcher_client.PatcherClient` with different credentials), but it has only been exercised against a single Jamf instance configured with two [sites](https://learn.jamf.com/en-US/bundle/jamf-pro-documentation-current/page/Sites.html). Multi-tenant patterns (one workstation hopping between two distinct Jamf Pro instances) should have no problem, but has not been *explicitly tested*. If you run into any issues, be sure to [submit an issue](https://github.com/liquidz00/Patcher/issues/new?template=bug_report.yml) and let us know about it.
