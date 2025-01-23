:html_theme.sidebar_secondary.remove: True

.. _cli:

============================
Command Line Interface (CLI)
============================

Entry Point
-----------

.. function:: cli(ctx: click.Context, debug: bool) -> None

    Main entry point for the CLI.

    :param ctx: The Click context object.
    :type ctx: click.Context
    :param debug: Enable debug logging if `True`.
    :type debug: :py:class:`bool`

    **Options**:
      - ``--debug``, ``-x``: Enable verbose logging.

Subcommands
-----------

.. admonition:: Added in version 2.0
    :class: success

    Patcher has been split into three separate commands; ``analyze``, ``reset`` and ``export``. For usage and examples, see our `Usage <usage>` page.

Reset Command
^^^^^^^^^^^^^

.. function:: reset(ctx: click.Context, kind: str, credential: Optional[str]) -> None

    Resets configurations based on the specified kind.

    **Arguments**:
      - ``ctx``: The Click context object.
      - ``kind``: The type of reset to perform. Options include:

        - ``full``: Resets all configurations.
        - ``UI``: Resets only the UI configurations.
        - ``creds``: Resets credentials.

    **Options**:
      - ``--credential``, ``-c``: Specify which credential to reset.


Export Command
^^^^^^^^^^^^^^

.. function:: export(ctx: click.Context, path: str, pdf: bool, sort: Optional[str], omit: bool, date_format: str, ios: bool, concurrency: int) -> None

    Exports patch management data in Excel and/or PDF formats.

    **Arguments**:
      - ``ctx``: The Click context object.
      - ``path``: File path to save the generated reports.
      - ``pdf``: Generate a PDF report if `True`.
      - ``sort``: Column to sort by.
      - ``omit``: Omit software titles released in the last 48 hours.
      - ``date_format``: Format of the date in the PDF header.
      - ``ios``: Include mobile device data if `True`.
      - ``concurrency``: Maximum number of API requests sent concurrently.


Analyze Command
^^^^^^^^^^^^^^^

.. function:: analyze(ctx: click.Context, excel_file: str, criteria: str, threshold: float, top_n: int, summary: bool, output_dir: Union[str, Path]) -> None

    Analyzes exported patch management data.

    **Arguments**:
      - ``ctx``: The Click context object.
      - ``excel_file``: Path to the Excel file to analyze.
      - ``criteria``: Criteria for filtering results.
      - ``threshold``: Threshold percentage for filtering.
      - ``top_n``: Limit the number of results displayed.
      - ``summary``: Generate a summary file if `True`.
      - ``output_dir``: Directory to save the summary.

