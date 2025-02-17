.. _export:

=======
Export
=======

The ``export`` command collects patch management data from Jamf API calls, subsequently exporting the data to **Excel, PDF, and HTML formats**. This command works hand-in-hand with the :meth:`~patcher.client.report_manager.ReportManager.process_reports` and :meth:`~patcher.utils.data_manager.DataManager.export` methods.

Parameters
----------

.. param:: path
    :type: str
    :required:

    The path to save the generated report(s).

.. param:: formats
    :type: list[str]

    If provided, only the specified formats will be exported. The option *must be specified multiple times* for multiple formats. 

    **Example Usage**

    - ``--format excel`` → exports Excel spreadsheet format only
    - ``--format html --format pdf`` → exports both HTML and PDF formats

    **Available Options**: ``excel``, ``pdf``, ``html``.

.. param:: sort
    :type: str

    Sort the patch reports by specifying a column.

    .. note::
        Patcher automatically handles column name conversion to match column titles in the data frame.

.. param:: omit
    :type: bool

    Omit software titles with patches released in last 48 hours.

.. _date-format:

.. param:: date_format
    :type: str

    Specify the date format for the PDF header. Default is ``"%B %d %Y"`` (Month Day Year):
    
    .. container:: sd-table

        .. list-table::
            :header-rows: 1
            :widths: auto

            * - Option
              - Description
              - Example
            * - **Month-Year**
              - Displays the date as the full month name followed by the year
              - January 2024
            * - **Month-Day-Year** *(default)*
              - Displays the date with the full month name, day and year
              - January 31 2024
            * - **Year-Month-Day**
              - Displays the date with the year followed by the full month name and day
              - 2024 April 21
            * - **Day-Month-Year**
              - Displays the date with the day followed by the full month name and year
              - 16 April 2024
            * - **Full**
              - Displays the full weekday name, followed by the full month name, day and year
              - Thursday September 26 2013
    
.. _ios:

.. param:: ios
    :type: bool

    If passed, includes iOS device data in exported reports.

.. _concurrency:

.. param:: concurrency
    :type: int

    The maximum number of API requests that can be sent at once. Defaults to 5.

    .. warning::
        Changing the max_concurrency value could lead to your Jamf server being unable to perform other basic tasks.
        It is **strongly recommended** to limit API call concurrency to no more than 5 connections.
        See `Jamf Developer Guide <https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices>`_ for more information.

Usage 
-----

.. card:: Export with default behavior (exports all formats)

    .. code-block:: console

        $ patcherctl export --path '/path/to/save'

.. card:: Export only specific formats (``--format``, ``-f``)

    .. code-block:: console

        $ patcherctl export --path '/path/to/save' --format excel
        $ patcherctl export --path '/path/to/save' --format html --format pdf

.. card:: Sort (``--sort``, ``-s``)

    .. code-block:: console

        $ patcherctl export --path '/path/to/save' --sort "Column Name"
    
.. card:: Omit (``--omit``, ``-o``)

    .. code-block:: console

        $ patcherctl export --path '/path/to/save' --omit
    
.. card:: Date Format (``--date-format``, ``-d``)

    .. code-block:: console

        $ patcherctl export --path '/path/to/save' --date-format "Month-Year"
    
.. card:: iOS (``--ios``, ``-m``)

    .. code-block:: console

        $ patcherctl export --path '/path/to/save' --ios
    
.. card:: Concurrency (``--concurrency``)

    .. code-block:: console

        $ patcherctl export --path '/path/to/save' --concurrency 10
