:html_theme.sidebar_secondary.remove: True

.. _export:

=======
Export
=======

**Description**: The ``export`` command collects patch management data from Jamf API calls, subsequently exporting the data to Excel spreadsheet and optional PDF formats. This command works hand-in-hand with the :meth:`~patcher.client.report_manager.ReportManager.process_reports` method.

Parameters
----------

- ``path`` (:py:class:`str`) (**Required**): 
    The path to save the generated report(s).

- ``pdf`` (:py:class:`bool`):
    Specifies whether or not to generate a PDF document in addition to Excel spreadsheet.

- ``sort`` (:py:obj:`~typing.Optional` [:py:class:`str`]):
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
    The maximum number of API requests that can be sent at once. Defaults to 5.

.. warning::
    Changing the max_concurrency value could lead to your Jamf server being unable to perform other basic tasks.
    It is **strongly recommended** to limit API call concurrency to no more than 5 connections.
    See `Jamf Developer Guide <https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices>`_ for more information.

Usage 
-----

.. card:: Sort (``--sort``, ``-s``)

    .. code-block:: console

        $ patcherctl export --path '/path/to/save' --sort "Column Name"
    
    .. note::
        Patcher automatically handles column name conversion to match column titles in the data frame. 
    
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
    