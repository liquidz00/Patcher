.. _usage:

=====
Usage
=====

The main entry point for the Patcher CLI (patcherctl).

.. admonition:: Added in version 2.0
    :class: success

    Patcher has been split into three separate commands; ``analyze``, ``reset`` and ``export``. Details and usage of each command are below.

Global Options & Info
---------------------

Exit Codes
^^^^^^^^^^

Patcher leverages specific exit codes depending on what type of error occurred at runtime:

.. container:: sd-table

   .. list-table::
      :header-rows: 1
      :widths: auto

      * - Exit Code
        - Description
      * - 0
        - Success
      * - 1
        - Handled exception (e.g., PatcherError or user-facing issue)
      * - 2
        - Unhandled exception
      * - 130
        - KeyboardInterrupt (Ctrl+C)

Debug Mode (verbose)
^^^^^^^^^^^^^^^^^^^^

Patcher accepts a global ``--debug`` (or ``-x``) flag to show debug log level messages and higher to standard out. This overrides the built in :class:`~patcher.utils.animation.Animator` from showing so no message conflicts occur. This flag is handled at the root CLI level and thus can be passed to any command.

.. code-block:: console

    $ patcherctl export --path '/path/to/save' --pdf --debug

Would result in a similar output to stdout as follows:

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

Export
------

**Description**: The ``export`` command collects patch management data from Jamf API calls, subsequently exporting the data to Excel spreadsheet and optional PDF formats. This command works hand-in-hand with the :meth:`~patcher.client.report_manager.ReportManager.process_reports` method.

Command Parameters (Export)
^^^^^^^^^^^^^^^^^^^^^^^^^^^

- ``ctx`` (`click.Context <https://click.palletsprojects.com/en/stable/api/#context>`_):
    The ``click.Context`` object, providing access to shared state between commands.

- ``path`` (:py:class:`str`):
    The path to save the generated report(s). (**Required**)

- ``pdf`` (:py:class:`bool`):
    Specifies whether or not to generate a PDF document in addition to Excel spreadsheet.

- ``sort`` (:py:obj:`~typing.Optional` of :py:class:`str`):
    Sort the patch reports by specifying a column.

- ``omit`` (:py:class:`bool`):
    Omit software titles with patches released in last 48 hours.

.. _date-format:

- ``date_format`` (:py:class:`str`):
    Specify the date format for the PDF header. Default is "%B %d %Y" (Month Day Year). Options:

    - **Month-Year**: Displays the date as the full month name followed by the year (e.g., January 2024)
    - **Month-Day-Year** (default): Displays the date with the full month name, day and year (e.g., January 31 2024)
    - **Year-Month-Day**: Displays the date with the year followed by the full month name and day (e.g., 2024 April 21)
    - **Day-Month-Year**: Displays the date with the day followed by the full month name and year (16 April 2024)
    - **Full**: Displays the full weekday name, followed by the full month name, day and year (Thursday September 26 2013)

.. _ios:

- ``ios`` (:py:class:`bool`):
    If passed, includes iOS device data in exported reports.

.. _concurrency:

- ``concurrency`` (:py:class:`int`):
    The maximum number of API requests that can be sent at once. Defaults to 5. See :ref:`Concurrency Usage <concurrency>`

Usage Examples (Export)
^^^^^^^^^^^^^^^^^^^^^^^

.. tab-set::

    .. tab-item:: Sort

        .. code-block:: console

            $ patcherctl export --path '/path/to/save' --sort "Column Name"

    .. tab-item:: Omit

        .. code-block:: console

            $ patcherctl export --path '/path/to/save' --omit

    .. tab-item:: Date Format

        .. code-block:: console

            $ patcherctl export --path '/path/to/save' --date-format "Month-Year"

    .. tab-item:: iOS



        .. code-block:: console

            $ patcherctl export --path '/path/to/save' --ios

    .. tab-item:: Concurrency

        .. code-block:: console

            $ patcherctl export --path '/path/to/save' --concurrency 10

.. _resetting_patcher:

Reset
------

**Description**: Allows for resetting of configurations based upon specified kind:

- ``full``: Resets credentials, UI elements, and property list file. Subsequently triggers :class:`~patcher.client.setup.Setup` to start setup.
- ``UI``: Resets UI elements of PDF reports (header & footer text, custom font and optional logo).
- ``creds``: Resets credentials stored in Keychain. Useful for testing Patcher in a non-production environment first. Allows specifying which credential to reset using the ``--credential`` option.

.. note::
    Options are not case-sensitive and are converted to lowercase automatically at runtime

Command Parameters (Reset)
^^^^^^^^^^^^^^^^^^^^^^^^^^

- ``kind`` (:py:class:`str`):
    Specifies the type of reset to perform. (**Required**)

- ``credential`` (:py:obj:`~typing.Optional` | :py:class:`str`):
    The specific credential to reset when performing credentials reset. Defaults to all credentials if none specified.

Usage Examples (Reset)
^^^^^^^^^^^^^^^^^^^^^^

.. tab-set::

    .. tab-item:: Reset All (Full)

        .. code-block:: console

            $ patcherctl reset full

        *This will reset all configurations (credentials, UI elements, and property list file) and initiate the setup process.*

    .. tab-item:: Reset UI Elements

        .. code-block:: console

            $ patcherctl reset UI

        *This is useful if you only need to refresh the appearance of generated reports (header/footer text or custom logos).*

    .. tab-item:: Reset All Credentials

        .. code-block:: console

            $ patcherctl reset creds

        *This will prompt you to provide new values for URL, Client ID, and Client Secret.*

    .. tab-item:: Reset Specific Credential

        .. code-block:: console

            $ patcherctl reset creds --credential url

        *You will be prompted to enter a new value for the credential specified to be reset.*

.. important::

    Performing a full credential reset will prompt for **all client credentials** (URL, Client ID, Client Secret).
    **Do not use this method** unless you are confident you have access to these credentials, especially if:

    - Your environment does **not** use SSO.
    - You relied on the automatic setup of Patcher (:attr:`~patcher.client.setup.SetupType.STANDARD`)

.. note::

    You can reset individual credentials by specifying one of the following options:

    - ``url``
    - ``client_id``
    - ``client_secret``

Analyze
-------

**Description**: Analyzes an exported patch report in Excel format and outputs analyzed results.

Command Parameters (Analyze)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- ``excel_file`` (:py:class:`str`):
    Path to the Excel file containing patch management data. (**Required**)

- ``threshold`` (:py:class:`float`):
    Filters software titles that are below the specified completion percentage.

- ``criteria`` (:py:class:`str`):
    Specifies the criteria for filtering patches. See :class:`~patcher.client.analyze.FilterCriteria`

    Options are:

    - :attr:`~patcher.client.analyze.FilterCriteria.MOST_INSTALLED`
    - :attr:`~patcher.client.analyze.FilterCriteria.LEAST_INSTALLED`
    - :attr:`~patcher.client.analyze.FilterCriteria.OLDEST_LEAST_COMPLETE`
    - :attr:`~patcher.client.analyze.FilterCriteria.BELOW_THRESHOLD`
    - :attr:`~patcher.client.analyze.FilterCriteria.RECENT_RELEASE`
    - :attr:`~patcher.client.analyze.FilterCriteria.ZERO_COMPLETION`
    - :attr:`~patcher.client.analyze.FilterCriteria.TOP_PERFORMERS`

- ``top_n`` (:py:class:`int`):
    Number of top entries to display based on the criteria. Default is ``None``, meaning all results will be returned.

- ``summary`` (:py:class:`bool`):
    If passed, will generate a summary file in ``.txt`` format in addition to showing results in stdout.

- ``output_dir`` (:py:obj:`~typing.Union` :py:class:`str` | :py:obj:`~pathlib.Path`):
    Path to save generated summary if ``--summary`` flag is passed.

Usage Examples (Analyze)
^^^^^^^^^^^^^^^^^^^^^^^^

.. tab-set::

    .. tab-item:: Analyze with Threshold

        .. code-block:: console

            $ patcherctl analyze /path/to/excel.xlsx --criteria below-threshold --threshold 50.0

        *Filters software titles with completion percentage below 50%. Use this to identify poorly adopted patches.*

    .. tab-item:: Analyze Most Installed

        .. code-block:: console

            $ patcherctl analyze /path/to/excel.xlsx --criteria most-installed

        *Displays software titles with the highest number of total installations.*

    .. tab-item:: Analyze Least Installed

        .. code-block:: console

            $ patcherctl analyze /path/to/excel.xlsx --criteria least-installed --top-n 5

        *Shows the top 5 least-installed software titles.* Use ``--top-n`` to limit results.

    .. tab-item:: Analyze Recent Releases

        .. code-block:: console

            $ patcherctl analyze /path/to/excel.xlsx --criteria recent-release

        *Filters for patches released in the last week. Use for tracking the adoption of new patches.*

        .. tip::
            :class: success

            Additionally, option is particularly useful for organizations with Service Level Agreements (SLAs) or policies that mandate installing new patches within a specific time frame (e.g., within 7 days of release).

    .. tab-item:: Analyze Zero Completion

        .. code-block:: console

            $ patcherctl analyze /path/to/excel.xlsx --criteria zero-completion

        *Displays software titles with 0% completion, helpful for identifying areas of complete non-adoption.*

    .. tab-item:: Analyze High Missing

        .. code-block:: console

            $ patcherctl analyze /path/to/excel.xlsx --criteria high-missing --top-n 10

        *Filters software titles where missing patches are greater than 50% of total hosts.* Use ``--top-n`` to limit results.

    .. tab-item:: Oldest Least Complete

        .. code-block:: console

            $ patcherctl analyze /path/to/excel.xlsx --criteria oldest-least-complete

        *Returns the oldest patches with the least completion percent.*

    .. tab-item:: Top Performers

        .. code-block:: console

            $ patcherctl analyze /path/to/excel.xlsx --criteria top-performers

        *Lists software titles with completion percentage above 90%. Great for showcasing successful patch adoption.*

.. admonition:: Important
    :class: warning

    The ``--summary`` option requires an output directory specified via ``--output-dir``. Ensure the directory exists and has write permissions before running the command. Otherwise, the summary file will not be generated.

