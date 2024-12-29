(jamf-guide)=

# Jamf Deployment Guide

This guide covers adding patch management/software titles, setting up an API Role & Client in Jamf Pro, and proper management of access tokens.

## Adding Software Titles

When utilizing the Patcher tool with Jamf Pro, it's important to understand that the tool exclusively pulls data from configured patch management titles. As it relies on the Jamf Pro API, patch data of software titles not available in the [Patch Management Software Titles](https://learn.jamf.com/en-US/bundle/jamf-app-catalog/page/Patch_Management_Software_Titles.html) list in Jamf App Catalog or Title Editor will **not be exported**. Therefore, ensure that all necessary software titles are properly configured within Jamf Pro to ensure accurate and comprehensive patch management.

Refer to [Configuring a Patch Management Software Title](https://learn.jamf.com/en-US/bundle/jamf-pro-documentation-current/page/Configuring_a_Patch_Management_Software_Title.html) in the Jamf Pro Documentation for instructions on setting up software titles for patch management purposes.

## Creating an API Role & Client

To utilize Patcher with Jamf Pro, you need to create an API Role and Client first. Reference the [Jamf Pro Documentation](https://learn.jamf.com/bundle/jamf-pro-documentation-current/page/API_Roles_and_Clients.html) or follow the steps below.

### API Role & Privileges

Before creating an API client, you must establish an API role with the necessary privileges:

1. Navigate to **Settings** in the Jamf Pro sidebar.
2. Under **System**, select **API Roles and Clients**.
3. Switch to the **API Roles** tab.
4. Click **New** to create a new role.
5. Provide a meaningful display name for the API role (e.g., "Patcher-Roles").
6. In the **Jamf Pro API Role privileges** field, type the following privileges required for use with Patcher
   - Read Patch Management Software Titles
   - Read Patch Policies
   - Read Mobile Devices
   - Read Mobile Device Inventory Collection
   - Read Mobile Device Applications
   - Read API Integrations
   - Read API Roles
   - Read Patch Management Settings
   - Update API Integrations
7. Click **Save** to create the role.

### API Client

Once your API role is ready, proceed to create an API client:

1. Follow steps 1-2 from above to navigate back to the **API Roles and Clients** section if not already there.
2. Click on the **API Clients** tab.
3. Select **New** to initiate a new API client creation.
4. Assign a clear and descriptive display name for the API client (e.g., "Patcher-Client").
5. In the **API Roles** field, assign the previously created API role to this client.
6. Define the **Access Token Lifetime**. This defines how long each token remains valid. See [Access Token Lifetime](#access-token-lifetime) below for more information.
7. Enable the API client by clicking **Enable API Client**.
8. Click **Save**.
9. Record the **Client ID** value for safe-keeping.

### Generating a Client Secret

:::{important}
Record the generated client secret immediately and securely as it is shown **only once**.
:::

1. Within Jamf Pro, go to the previously created API client's details page.
2. Click **Generate Client Secret** to create a new secret.
3. Confirm the action in the dialog box by selecting **Create Secret**.
4. The client secret will now be displayed.

You can now pass the client ID and client secret values when prompted by the setup assistant. The Jamf URL, client ID, client secret, and access token are all saved to keychain and can be modified if necessary.

## Access Token Lifetime

:::{note}
Generating an access token is not required. Patcher handles obtaining and refreshing of tokens automatically. See {class}`~patcher.token_manager.TokenManager` for more.
:::

When defining the access token lifetime, it is recommended to use a duration of at least 5 minutes. Patcher is designed to handle automatic token refreshing and generation. Longer durations reduce the frequency of token regeneration, thereby decreasing administrative overhead. However, ensure that the chosen duration aligns with your organization's security policies.

### Token Generation

In situations where AccessTokens *need* to be generated manually, copy the bash script below into the code editor of your choice. Substitute your Jamf Pro URL in the `url` variable, and modify the `client_id` and `client_secret` values with the Client ID and secret generated from the steps above.

:::{note}

If using the Python version below, be sure to install the `requests` and `keyring` libraries first: 
```console
$ pip install requests keyring
```
:::

::::{tab-set}

:::{tab-item} Command Prompt
```shell
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

echo "Token: $token"
echo "Expiration: $token"

keychain_service="Patcher"

security add-generic-password -a "TOKEN" -s "$keychain_service" -w "$token" -U
security add-generic-password -a "TOKEN_EXPIRATION" -s "$keychain_service" -w "$expires_in" -U

echo "Token and expiration time have been saved to the Keychain."
```
:::

:::{tab-item} Python

```python
import requests
import keyring

# Define the server URL and API credentials
url = "https://yourserver.jamfcloud.com/api/oauth/token"
client_id = "your-jamf-api-client-id"
client_secret = "your-jamf-api-client-secret"

# Prepare the request payload and headers
payload = {
    'client_id': client_id,
    'grant_type': 'client_credentials',
    'client_secret': client_secret
}
headers = {
    'Content-Type': 'application/x-www-form-urlencoded'
}

# Send the POST request to retrieve the token
response = requests.post(url, data=payload, headers=headers)

# Check if the response was successful
if response.status_code != 200:
  # Raise an exception with a custom error message
  raise ValueError(f"Failed to retrieve the token. Status Code: {response.status_code}, Message: {response.text}")

# Extract the token and expiration time from the JSON response
data = response.json()
token = data.get('access_token')
expires_in = data.get('expires_in')

# Output the token and expiration time
print(f"Token: {token}")
print(f"Expiration: {expires_in}")

# Define keychain service name and account
keychain_service = "Patcher"
token_account = "TOKEN"
expiration_account = "TOKEN_EXPIRATION"

# Save the token and expiration time to the keychain
keyring.set_password(keychain_service, token_account, token)
keyring.set_password(keychain_service, expiration_account, str(expires_in))

print("Token and expiration time have been saved to the Keychain.")
```
:::

::::

If successful, the script(s) above will print the `access_token` and `expires_in` values to the console *and* save them to the login keychain. 
