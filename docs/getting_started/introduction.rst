============
Introduction
============

Patcher is an innovative tool designed for Mac Admins. Leveraging the Jamf Pro API, Patcher streamlines the process of fetching patch management data and generating comprehensive reports, facilitating efficient tracking and reporting on software update compliance across macOS devices managed through Jamf Pro.

Features
^^^^^^^^

- **Real-Time Patch Information Export**: Quickly extract up-to-date patch data for analysis.
- **Excel Spreadsheet Integration**: Seamlessly export patch information into Excel for in-depth analysis and record-keeping.
- **PDF Reporting**: Generate neatly formatted PDFs for easy sharing and documentation of patch statuses.
- **Customization Options**: Tailor the tool to meet your specific reporting and analysis needs.

Prerequisites
-------------

Ensure you have Python 3.10 or higher, and access to a Jamf Pro instance with administrator privileges. It is **required** to create a dedicated API client for Patcher use, with the following roles:

- Read Patch Management Software Titles
- Read Patch Policies
- Read Mobile Devices
- Read Mobile Device Inventory Collection
- Read Mobile Device Applications
- Read API Integrations
- Read API Roles
- Read Patch Management Settings

Refer to the `Jamf Pro Documentation <https://learn.jamf.com/bundle/jamf-pro-documentation-current/page/API_Roles_and_Clients.html>`_ on API Roles and Clients for more information.
