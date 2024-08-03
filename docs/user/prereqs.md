# Prerequisites

Ensure you have Python 3.10 or higher, and access to a Jamf Pro instance with administrator privileges.

```{tip}
**For versions 1.3.4 and later**: Patcher can automatically handle the creation of API clients and roles, provided SSO is not used for Jamf Pro accounts. If SSO is used, you will need to manually create and provide an API client and role for Patcher.
```

If manual creation is required, create a dedicated API client for Patcher use. Reference the {ref}`Jamf Deployment Guide <jamf-guide>` for assistance.

```{dropdown} Still have questions on API Roles and Clients?
Refer to the [Jamf Pro Documentation](https://learn.jamf.com/bundle/jamf-pro-documentation-current/page/API_Roles_and_Clients.html) on API Roles and Clients for more information.
```
