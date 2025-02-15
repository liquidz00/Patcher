.. _installomator:

=====================
Installomator Support
=====================

.. Utilize ghwiki extension as much as possible with format "Custom Link Text <Repo:Page#Header>"

.. admonition:: Disclaimer
    :class: warning

    While every effort is made to match software titles accurately, Installomator remains the **source of truth** for label definitions. If ever unsure about a match, verify the label directly within `Installomator's <https://github.com/Installomator/Installomator>`_ repository.

What is Installomator?
----------------------

Installomator is an open-source tool designed for automated software installation and management on macOS. It is widely used by MacAdmins to streamline application deployment via MDMs such as Jamf Pro. Installomator retrieves and installs software directly from vendor sources, simplifying the process of keeping applications up to date without requiring manually built packages. Unlike traditional methods, it dynamically determines installation parameters, making it highly flexible and efficient.

Storing Labels
--------------

Instead of fetching label definitions dynamically from the Installomator repository each time the CLI runs, labels are stored locally in ``~/Library/Application Support/Patcher/.labels``. This reduces network overhead and speeds up label matching operations. The stored labels are periodically updated to ensure they remain accurate and up to date.

Matching Process
----------------

Patcher matches software titles to Installomator labels using multiple methods to ensure the most accurate results:

- **Direct Matching**: Compares application names directly against Installomator label names.

.. literalinclude:: ../../src/patcher/utils/installomator.py
    :lines: 176-185
    :language: python

- **Fuzzy Matching**: Uses similarity scoring (via `rapidfuzz <https://rapidfuzz.github.io/RapidFuzz/>`_) to find the best-matching label when a direct match isn't found.

.. literalinclude:: ../../src/patcher/utils/installomator.py
    :lines: 187-196
    :language: python

- **Normalized Matching**: In the event a match is not found via a direct or fuzzy match, the software titles name is 'normalized' and checked against all labels (e.g., ``Node.js`` → ``nodejs``).

.. literalinclude:: ../../src/patcher/utils/installomator.py
    :lines: 198-236
    :language: python

Why Matching Can Be Tricky
^^^^^^^^^^^^^^^^^^^^^^^^^^

One of the biggest challenges in matching software titles to Installomator labels is inconsistency in naming conventions.

Take 'Zoom' for example:

- The software title is referenced as **Zoom Client for Meetings** in Jamf Pro
- The application name is ``zoom.us.app``
- Installomator labels are ``zoom``, ``zoomclient``, ``zoomgov`` and others.

.. _app_name_response:

To retrieve corresponding Application names for Software Titles, a separate call to the Jamf Pro API is made to the ``/api/v2/patch-software-title-configurations/{title_id}/definitions`` endpoint. The response payload scheme is formatted as follows:

.. code-block:: json
    :caption: `Jamf Developer Docs <https://developer.jamf.com/jamf-pro/reference/get_v2-patch-software-title-configurations-id-definitions>`_

    {
      "totalCount": 1,
      "results": [
        {
          "version": "10.37.0",
          "minimumOperatingSystem": "12.0.1",
          "releaseDate": "2010-12-10 13:36:04",
          "rebootRequired": false,
          "killApps": [
            {
              "appName": "Firefox"
            }
          ],
          "standalone": false,
          "absoluteOrderId": "1"
        }
      ]
    }

When present, all ``appName`` values are appended to a list and returned along with the software title (:class:`~patcher.models.patch.PatchTitle`) name. This mapping is then normalized and used to intelligently match titles across different naming formats.

Unmatched Applications
^^^^^^^^^^^^^^^^^^^^^^

Applications that are still not matched after matching attempts are written to JSON file at ``~/Library/Application Support/Patcher/unmatched_apps.json``. This can be helpful in order to review unmatched applications and manually create labels if needed.

An example of this file could look like:

.. code-block:: json

    [
        {
            "Patch": "Appium",
            "App Names": [
                "Appium"
            ]
        },
        {
            "Patch": "Adobe Illustrator",
            "App Names": [
                "Adobe Illustrator"
            ]
        }
    ]

Understanding the JSON Format
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The JSON file will consist of a list of objects, where each object represents a software title that could not be matched with an Installomator label. Each object contains the following keys:

- ``"Patch"`` (*string*): The ``title`` attribute of the :class:`~patcher.models.patch.PatchTitle` in question.
- ``"App Names"`` (*list of strings*): The application names extracted from the :ref:`Jamf API response <app_name_response>` (if present), corresponding to that software title.

How This Data Is Used
~~~~~~~~~~~~~~~~~~~~~~

- If an Installomator label is later added for an application, it will be removed from ``unmatched_apps.json`` during the next match attempt.
- The presence of ``App Names`` helps identify applications with multiple labels (e.g., ``zulujdk8``, ``zulujdk9``). :class:`~patcher.models.patch.PatchTitle` objects store these labels in the ``install_label`` list attribute.
- Users can use this file to :ghwiki:`manually create labels <Installomator:Label Variables Reference#building a new label>` or report missing mappings.

Ignored Software Titles
-----------------------

Certain software titles are **explicitly ignored** by Patcher as they are typically not patched via automated means or have deprecated support. These applications usually rely on system updates (e.g., macOS updates via Apple's software update mechanism) or other vendor-specific mechanisms.

.. admonition:: How This Affects Matching
    :class: warning

    Any software title in this list **will be ignored** and **will not be matched** to Installomator label, even if one exists.

Below is the current list of ignored titles:

.. code-block:: python
    :caption: List of Ignored Software Titles

    IGNORED_TITLES = [
        "Apple macOS *",
        "Oracle Java SE *",
        "Eclipse Temurin *",
        "Apple Safari",
        "Apple Xcode",
        "Microsoft Visual Studio",
    ]

Why These Titles Are Ignored
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- **Apple software (macOS, Safari, Xcode)**: Managed either by MDM or Apple's software update mechanism.
- **Java and Eclipse Temurin**: Often require manual intervention for licensing and security compliance.
- **Microsoft Visual Studio**: This refers to the full Visual Studio for Mac IDE, which `has been deprecated by Microsoft as of August 2024 <https://devblogs.microsoft.com/visualstudio/visual-studio-for-mac-retirement-announcement/>`_.

.. note::

    *Microsoft Visual Studio Code* is not affected by this deprecation and remains supported.

Retrieving Label Details
~~~~~~~~~~~~~~~~~~~~~~~~

Currently, Patcher only provides a **Y/N** response indicating whether an Installomator label exists for a given software title. Future updates will enhance this by allowing retrieval of full label details, including installation parameters.

Upcoming Features
-----------------

Installomator features are currently in beta (``v2.0.4b1``) as we build onto this base functionality. We are actively working on implementing:

- Policy creation in Jamf for supported titles with available :ghwiki:`script options <Installomator:Configuration and Variables>`
- An option to completely disable Installomator support should it not align with your organizations security standards or preferences
- Integration with `AutoPkg <https://github.com/autopkg/autopkg>`_ to expand package deployment capabilities

