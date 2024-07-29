.. _cli:

======================
Command Line Interface
======================

.. note::

    The CLI entry point collaborates with the :mod:`~patcher.client.report_manager` module. Most of the operations are managed by the Report Manager class, where debug logs are also generated, rather than within the CLI entry point.

The main entry point for the Patcher CLI (patcherctl).

Parameters
----------

- **ctx** (*click.Context*):
  Click context object. Used to ensure either the ``--path`` argument OR the ``--reset`` argument is supplied at runtime.

- **path** (*AnyStr*):
  The path to save the report(s).

- **pdf** (*bool*):
  If passed, Patcher will generate a PDF report along with the Excel spreadsheet using the :mod:`~patcher.models.reports.pdf_report` model.

- **sort** (*Optional[AnyStr]*):
  Sort patch reports by a specified column.

  .. note::
      Patcher handles the automatic conversion of the column name on your behalf. For example, if sorting by completion percent, simply pass "Completion Percent" at runtime.

- **omit** (*bool*):
  If passed, software titles with patches released in the last 48 hours will be omitted from the exported report(s).

- **date_format** (*AnyStr*):
  Specify the date format for the PDF header from predefined choices. See :ref:`date format <date-format>` for more information.

- **ios** (*bool*):
  Include the amount of enrolled mobile devices on the latest version of their respective OS. This flag uses `SOFA <https://sofa.macadmins.io>`_ to pull latest iOS versioning data.

- **concurrency** (*int*):
  Set the maximum concurrency level for API calls.

  .. danger::
      Before using this argument, **please see** the :ref:`concurrency <concurrency>` documentation first.

- **debug** (*bool*):
  Enable debug logging to see detailed debug messages. Providing this option replaces the animation usually shown to ``stdout``.

- **reset** (*bool*):
  Resets the ``config.ini`` file used for customizable elements in exported PDF reports, then triggers :func:`~patcher.client.setup._setup_ui` method. See :ref:`Customizing Reports <customize_reports>` for more information.
