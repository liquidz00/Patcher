.. _getting_started_index:

===============
Getting Started
===============

Patcher is an innovative tool designed for Mac Admins. Leveraging the Jamf Pro API, Patcher streamlines the process of fetching patch management data and generating comprehensive reports, facilitating efficient tracking and reporting on software update compliance across macOS devices managed through Jamf Pro.

Features
^^^^^^^^

- **Real-Time Patch Information Export**: Quickly extract up-to-date patch data for analysis.
- **Excel Spreadsheet Integration**: Seamlessly export patch information into Excel for in-depth analysis and record-keeping.
- **PDF Reporting**: Generate neatly formatted PDFs for easy sharing and documentation of patch statuses.
- **Customization Options**: Tailor the tool to meet your specific reporting and analysis needs.

Prerequisites
-------------

Ensure you have Python 3.10 or higher, and access to a Jamf Pro instance with administrator privileges.

.. tip::

    **For versions 1.3.4 and later**: Patcher can automatically handle the creation of API clients and roles, provided SSO is not used for Jamf Pro accounts. If SSO is used, you will need to manually create and provide an API client and role for Patcher.

If manual creation is required, create a dedicated API client for Patcher use. Reference the :ref:`Jamf Deployment Guide <jamf-guide>` for assistance.

.. dropdown:: Still have questions on API Roles and Clients?

    Refer to the `Jamf Pro Documentation <https://learn.jamf.com/bundle/jamf-pro-documentation-current/page/API_Roles_and_Clients.html>`_ on API Roles and Clients for more information.

Installation
============

Once prerequisites have been satisfied, Patcher can be installed via ``pip``:

.. code-block:: console

    $ python3 -m pip install --upgrade patcherctl

Optionally, beta releases of Patcher are released to `Test PyPI <https://test.pypi.org/project/patcherctl/>`_ and can be installed via the following command:

.. code-block:: console

    $ python3 -m pip install -i https://test.pypi.org/simple --extra-index-url https://pypi.org/simple patcherctl=={VERSION}

Where ``{VERSION}`` is the beta version you are looking to install, e.g. ``1.3.4b2``.

.. note::
    Installing beta versions of Patcher are meant only for testing features being developed and implemented. We encourage installing these versions for contribution purposes. For more information, visit the :ref:`contributing <contributing_index>` page.

.. toctree::
    :maxdepth: 2
    :hidden:

    setup
