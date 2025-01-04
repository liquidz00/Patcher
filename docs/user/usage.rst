.. _usage:

=====
Usage
=====

The main entry point for the Patcher CLI (patcherctl).

.. admonition:: Added in version 2.0
    :class: success

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
