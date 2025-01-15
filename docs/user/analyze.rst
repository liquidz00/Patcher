:html_theme.sidebar_secondary.remove: True

.. _analyze:

=======
Analyze
=======

Analyzes an exported patch report in Excel format and outputs analyzed results.

Parameters
----------

- ``excel_file`` (:py:class:`str`):
    *(Optional)* Path to the Excel file containing patch management data.

    .. seealso::

        :ref:`Data caching <caching>`

- ``threshold`` (:py:class:`float`):
    Filters software titles that are below the specified completion percentage.

- ``criteria`` (:py:class:`str`):
    Specifies the criteria for filtering patches. See :class:`~patcher.client.analyze.FilterCriteria`. Options are:

    - ``most_installed``
    - ``least_installed``
    - ``oldest-least-complete``
    - ``below-threshold``
    - ``recent-release``
    - ``zero-completion``
    - ``top-performers``

- ``top_n`` (:py:class:`int`):
    Number of top entries to display based on the criteria. Default is ``None``, meaning all results will be returned.

- ``summary`` (:py:class:`bool`):
    If passed, will generate a summary file in ``.txt`` format in addition to showing results in stdout.

- ``output_dir`` (:py:obj:`~typing.Union` [:py:class:`str` | :py:obj:`~pathlib.Path`]):
    Path to save generated summary if ``--summary`` flag is passed.

Usage
-----

.. card:: Analyze with Threshold

    .. code-block:: console

        $ patcherctl analyze /path/to/excel.xlsx --criteria below-threshold --threshold 50.0
    +++
    Filters software titles with completion percentage below 50%.

.. card:: Analyze Most Installed

    .. code-block:: console

        $ patcherctl analyze /path/to/excel.xlsx --criteria most-installed
    +++
    Displays software titles with the highest number of total installations.

.. card:: Analyze Least Installed

    .. code-block:: console

        $ patcherctl analyze /path/to/excel.xlsx --criteria least-installed --top-n 5
    +++
    Shows the top 5 least-installed software titles. Use ``--top-n`` to limit results.

.. card:: Analyze Recent Releases

    .. code-block:: console

        $ patcherctl analyze /path/to/excel.xlsx --criteria recent-release

    .. tip::
        :class: success

        Additionally, option is particularly useful for organizations with Service Level Agreements (SLAs) or policies that mandate installing new patches within a specific time frame (e.g., within 7 days of release).
    +++
    Filters for patches released in the last week.

.. card:: Analyze Zero Completion

    .. code-block:: console

        $ patcherctl analyze /path/to/excel.xlsx --criteria zero-completion
    +++
    Displays software titles with 0% completion.

.. card:: Analyze High Missing

    .. code-block:: console

        $ patcherctl analyze /path/to/excel.xlsx --criteria high-missing --top-n 10
    +++
    Filters software titles where missing patches are greater than 50% of total hosts. Use ``--top-n`` to limit results.

.. card:: Oldest Least Complete

    .. code-block:: console

        $ patcherctl analyze /path/to/excel.xlsx --criteria oldest-least-complete
    +++
    Returns the oldest patches with the least completion percent.

.. card:: Top Performers

    .. code-block:: console

        $ patcherctl analyze /path/to/excel.xlsx --criteria top-performers
    +++
    Lists software titles with completion percentage above 90%.


.. admonition:: Important
    :class: warning

    The ``--summary`` option requires an output directory specified via ``--output-dir``. Ensure the directory exists and has write permissions before running the command. Otherwise, the summary file will not be generated.
