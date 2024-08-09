.. _usage:

=========
Usage
=========

Additional options that can be passed to Patcher. These additional options enable users to customize the generation of patch reports according to their specific requirements.

Sorting
-------

The ``--sort`` option allows users to sort patch reports based upon a specified column. This option is designed to help users organize their reports more efficiently and improve readability.

To use the ``--sort`` option, add ``--sort`` or ``-s`` followed by the column nameyou want to sort the report by. Patcher will automatically handle column name conversion to match column titles in the data frame.

.. code-block:: console

    $ patcherctl --path '/path/to/save' --sort "Column Name"

Ensure that the column name provided is valid and exists in the report. Invalid column names will result in an error and the script will abort.

Omit
----

The ``--omit`` option enables users to omit software titles from the report that have had patches released in the last 48 hours. This can be particularly useful for focusing on older, potentially unaddressed vulnerabilities. Additionally, this will allow for a more accurate total patch percentage if submitting reports to security or compliance departments.

No additional arguments are required for the omit option. It is simply a flag that can be passed to Patcher:

.. code-block:: console

    $ patcherctl --path '/path/to/save' --omit

.. _date-format:

Date Format
-----------

Specify the format of the date used in the header of exported PDF reports. This feature enables user to tailor the date presentation to their preferences or requirements, enhancing the reports' readability and context understanding.

To use the ``--date-format`` option, add ``-d`` or ``--date-format`` followed by one of the predefined format names.

.. code-block:: console

    $ patcherctl --path '/path/to/save' --date-format "Month-Year"

Options:
^^^^^^^^

- **Month-Year**: Displays the date as the full month name followed by the year (e.g., January 2024)
- **Month-Day-Year** (default): Displays the date with the full month name, day and year (e.g., January 31 2024)
- **Year-Month-Day**: Displays the date with the year followed by the full month name and day (e.g., 2024 April 21)
- **Day-Month-Year**: Displays the date with the day followed by the full month name and year (16 April 2024)
- **Full**: Displays the full weekday name, followed by the full month name, day and year (Thursday September 26 2013)

Ensure to select a format name exactly as listed to avoid errors. Invalid format names will result in an error, and the script will abort.

.. _ios:

iOS
---

The ``--ios`` or ``-m`` flags will append the amount of enrolled mobile devices on the latest version of iOS to the end of the data set. This option utilizes `SOFA <https://sofa.macadmins.io>`_, which reports on iOS versions 16 & 17. This means mobile devices on versions lower than iOS 16 will not be included in the report.

Similar to the ``--omit`` option, the ``--ios`` option is a flag. To include iOS data information in your report, simply pass the ``--ios`` or ``-m`` arguments to Patcher.

.. code-block:: console

    $ patcherctl --path '/path/to/save' --ios

Debug
-----

Passing ``--debug`` or ``-x`` to Patcher will output debug logs to standard out instead of showing the default animation message. This is meant to assist in troubleshooting issues by providing insight into what is going on behind the scenes.

Usage & Sample output
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: console

    $ patcherctl --path '/path/to/save' --debug

.. code-block:: text

    DEBUG: Checking bearer token validity
    DEBUG: Bearer token passed validity checks.
    DEBUG: Verifying token lifetime is greater than 5 minutes
    DEBUG: Token lifetime verified successfully.
    DEBUG: Beginning Patcher process...
    DEBUG: Validating path provided is not a file...
    DEBUG: Output path '/path/to/save' is valid.
    DEBUG: Attempting to create directories if they do not already exist...
    DEBUG: Reports directory created at '/path/to/save'.
    DEBUG: Attempting to retrieve policy IDs.
    DEBUG: Retrieved policy IDs for X policies.
    DEBUG: Attempting to retrieve patch summaries.
    DEBUG: Received policy summaries for X policies.
    DEBUG: Generating excel file...
    DEBUG: Excel file generated successfully at '/path/to/save/Patch-Reports/patch-report-07-05-24.xlsx'.
    DEBUG: Patcher finished as expected. Additional logs can be found at '~/Library/Application Support/Patcher/logs'.
    DEBUG: 41 patch reports saved successfully to /path/to/save/Patch-Reports.


.. _concurrency:

Concurrency
-----------

.. warning::
    Use caution when using this option. Higher concurrency settings can cause your Jamf server to become overloaded and fail to perform other basic functions. For more information, reference `Jamf Developer documentation <https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices#rate-limiting>`_ on rate limiting.

The ``--concurrency`` option sets the *maximum* number of concurrent API requests. By default, this is set to 5. Passing in a different integer to this option will modify this setting.

.. code-block:: console

    $ patcherctl --path '/path/to/save' --concurrency 10

Reset
-----

.. note::
    Using this option eliminates the need for the --path argument.

To streamline the customization process, you can use the ``--reset`` flag with Patcher. This option will clear the existing header and footer text from the PDF configuration and initiate the UI setup process again. This allows you to specify a custom font and modify the header and footer text options.

.. code-block:: console

    $ patcherctl --reset

.. _custom-ca:

Custom CA File
--------------

Pass a path to a ``.pem`` certificate to use as the default `SSL context <https://docs.python.org/3/library/ssl.html#context-creation>`_. Can be useful if running into SSL Validation Errors when using Patcher.

.. code-block:: console

    $ patcherctl --custom-ca-file '/path/to/.pem/file'

.. seealso::
    :class: dropdown

    :ref:`ssl-verify` on the installation page

