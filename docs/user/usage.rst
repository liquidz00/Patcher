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

.. _caching:

Data Caching
------------

Starting with version 2.0, Patcher now leverages data caching to improve performance and provide efficient handling of patch data. The cached data is stored in the user library cache directory (``~/Library/Caches/Patcher``).

Caching Behavior
^^^^^^^^^^^^^^^^

- **Enabled by Default**: Cached data is stored as `pickle files <https://docs.python.org/3.12/library/pickle.html>`_ (``*.pkl``) for quick reuse.
- **Automatic Cleaning**: Cache files older than *30 days* are automatically removed to save disk space.
- **Disabling Caching**: Caching can be disabled at any time by passing the ``--disable-cache`` flag with any command at runtime.

Managing Cached Data
^^^^^^^^^^^^^^^^^^^^

The following commands are available to assist in managing cache data:

1. **View Cached Files**:

    To inspect cached data, you can manually navigate to the cache directory:

    .. code-block:: console

        $ open ~/Library/Caches/Patcher

2. **Reset Cache**:

    The contents of the cache directory can be removed with the ``reset`` command:

    .. code-block:: console

        $ patcherctl reset cache
        ✅ Reset finished successfully.

3. **Disabling Cache**:

    Add the ``--disable-cache`` flag to any command to temporarily disable caching:

    .. code-block:: console

        $ patcherctl export --path /path/to/save --disable-cache

4. **Load Cached Data** (for Analysis):

    If cached data exists, the :ref:`analyze <analyze>` command will automatically use it unless you provide an alternate file via the ``--excel-file`` option:

    .. code-block:: console

        $ patcherctl analyze --criteria most-installed --threshold 75

    If no objects meet the criteria, a warning will be displayed to ``stdout``.

Automatic Cache Cleaning
^^^^^^^^^^^^^^^^^^^^^^^^

As mentioned previously, cache files older than 30 days are automatically cleaned each time data is cached or retrieved. This is designed to ensure efficient use of disk space.
