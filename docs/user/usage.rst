.. _usage:

=====
Usage
=====

The main entry point for the Patcher CLI (patcherctl).

.. admonition:: Added in version 2.0
    :class: tip

    Patcher has been split into three separate commands; :ref:`Analyze <analyze>`, :ref:`Export <export>`, and :ref:`Reset <reset>`


Viewing Help
------------

Patcher accepts both ``--help`` and ``-h`` parameters to view the help menu. Additionally, help is available for each subcommand and can be viewed by executing ``patcherctl <command> --help``.

.. code-block:: console

    $ patcherctl --help

.. container:: sd-table

    .. list-table::
       :header-rows: 1
       :widths: auto

       * - Option
         - Description
       * - ``--version``
         - Show the version and exit.
       * - ``-x``, ``--debug``
         - Enable debug logging (verbose mode).
       * - ``-h``, ``--help``
         - Show this message and exit.

.. _exit-codes:

Exit Codes
----------

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
      * - 4
        - API error (e.g., unauthorized, invalid response)
      * - 130
        - KeyboardInterrupt (Ctrl+C)

.. _debug:

Debug Mode (verbose)
--------------------

Patcher accepts a global ``--debug`` (or ``-x``) flag to show debug log level messages and higher to standard out. This overrides the built in :class:`~patcher.utils.animation.Animation` from showing so no message conflicts occur. This flag is handled at the root CLI level and thus can be passed to any command.

.. code-block:: console

    $ patcherctl export --path '/path/to/save' --pdf --debug

Would result in a similar output as:

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

Command Dependencies
--------------------

The :ref:`analyze <analyze>` command is tightly integrated with the :ref:`export <export>` command. It is important to understand this dependency for using Patcher effectively. 

Key Points
^^^^^^^^^^

- **Export Command Requirement**: The ``export`` command caches patch report data for later use by the ``analyze`` command, ensuring the data is available for analysis without having to run multiple export commands. 
- **Alternative Input**: The ``analyze`` command can accept patch reports via the ``--excel-file`` option, but these files *must* adhere to the schema of an exported patch report to prevent errors. Refer to the exported report structure for details.

Example Workflow
~~~~~~~~~~~~~~~~

.. code-block:: console
    :caption: Export patch reports.

    $ patcherctl export --path /path/to/save --pdf

.. code-block:: console
    :caption: Analyze command with cached reports

    $ patcherctl analyze --criteria most-installed --threshold 75

.. code-block:: console
    :caption: Analyze command with compatible patch report file

    $ patcherctl analyze --excel-file /path/to/patch-report.xlsx --criteria least-installed

.. note::

    If no objects meet the specified criteria during analysis, a warning will be displayed:

    .. code-block:: console

        $ patcherctl analyze --criteria below-threshold
        ⚠️ No PatchTitle objects meet criteria FilterCriteria.BELOW_THRESHOLD

Avoiding Errors
~~~~~~~~~~~~~~~

- Verify that exported patch reports are up-to-date before running the ``analyze`` command. 
- Double-check that manually provided files conform to the patch report schema to avoid processing errors. 

.. _caching:

Data Caching
------------

Starting with version 2.0, Patcher now leverages data caching to improve performance and provide efficient handling of patch data. The cached data is stored in the user library cache directory (``~/Library/Caches/Patcher``).

Caching Behavior
^^^^^^^^^^^^^^^^

- **Enabled by Default**: Cached data is stored as `pickle files <https://docs.python.org/3.12/library/pickle.html>`_ (``*.pkl``) for quick reuse.
- **Automatic Cleaning**: Cache files older than *90 days* are automatically removed to save disk space.
- **Disabling Caching**: Caching can be disabled at any time by passing the ``--disable-cache`` flag with any command at runtime.

Managing Cached Data
~~~~~~~~~~~~~~~~~~~~

The following commands are available to assist in managing cache data:

.. code-block:: console
    :caption: Manually navigate to the cache directory to inspect cache data.

    $ open ~/Library/Caches/Patcher

.. code-block:: console
    :caption: Remove cache directory contents with the ``reset`` command.

    $ patcherctl reset cache
    ✅ Reset finished successfully.

.. code-block:: console
    :caption: Add the ``--disable-cache`` flag to any command to temporarily disable caching.

    $ patcherctl export --path /path/to/save --disable-cache


Automatic Cache Cleaning
^^^^^^^^^^^^^^^^^^^^^^^^

Cache files older than 90 days are automatically cleaned each time data is cached or retrieved. This is designed to ensure efficient use of disk space while providing an ample time range for trend analysis.
