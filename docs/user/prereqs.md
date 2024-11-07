# Prerequisites

Ensure you have the following before proceeding with the installation and setup of Patcher:

- **Python 3.10 or Higher**: Make sure Python is installed on your system. You can download it from [python.org](https://www.python.org/downloads/). 
- **Access to a Jamf Pro Instance**: You need an instance of Jamf Pro with administrator privileges to perform setup tasks.

:::{versionadded} 1.3.5
Patcher can automatically handle the creation of API clients and roles, provided [SSO is not used for Jamf Pro accounts](https://developer.jamf.com/jamf-pro/docs/jamf-pro-api-overview#authentication-and-authorization). If SSO is used, you can either manually create an API Role & Client, *or* you can create a standard user account with admin privileges to pass to the setup assistant. 
:::

## Handling SSO in Jamf Pro

If your Jamf Pro environment uses Single Sign-On (SSO), follow the instructions below to ensure proper integration with Patcher:

### Option 1: Manual API Role and Client Creation

1. **Create an API Client and Role Manually**:
    - Log in to your Jamf Pro instance with an administrator account. 
    - Navigate to the **Settings** section and select **API Roles and Clients**. 
    - Create a new API role and client specifically for Patcher usage. 
    - Assign the necessary permissions for Patcher to function correctly. 

   For more detailed guidance, please refer to the {ref}`Jamf Deployment Guide <jamf-guide>` or consult your system administrator for assistance.
2. **Provide API Credentials**:
    - Once the API role and client are created, provide the credentials to the Patcher setup assistant as required. 

### Option 2: Temporary Standard User Account

1. **Create a Temporary Standard User Account**:
    - Temporarily [create a standard Jamf Pro user account](https://learn.jamf.com/en-US/bundle/jamf-pro-documentation-current/page/Jamf_Pro_User_Accounts_and_Groups.html#ariaid-title3:~:text=Click%20Save%20.-,Creating%20a%20Jamf%20Pro%20User%20Account,-Requirements) with administrator privileges. 
    - Pass this account to the setup assistant when prompted, which will automatically handle the creation of API objects.
   
2. **Remove the Temporary Account**:
    - After setup has completed, delete the temporary account to maintain security standards.

:::{seealso}
Refer to the [Jamf Pro Documentation](https://learn.jamf.com/bundle/jamf-pro-documentation-current/page/API_Roles_and_Clients.html) on API Roles and Clients for more information on creating roles and clients.
:::
