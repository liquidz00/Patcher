.. _analyze:

=======
Analyze
=======

Analyzes an exported patch report in Excel format and outputs analyzed results. The Analyzer class works in conjunction with :class:`~patcher.utils.data_manager.DataManager` objects to retrieve cached data and stored :class:`~patcher.models.patch.PatchTitle` objects.


Parameters
----------

- ``excel_file`` (:py:class:`str`):
    *(Optional)* Path to the Excel file containing patch management data.

- ``all_time`` (:py:class:`bool`):
    Allows for analyzation of patch report trends across all cached data instead of a single dataset. See :class:`~patcher.client.analyze.TrendCriteria`.

- ``threshold`` (:py:class:`float`):
    Filters software titles that are below the specified completion percentage.

- ``criteria`` (:py:class:`str`):
    Specifies the criteria for filtering patches. See :class:`~patcher.client.analyze.FilterCriteria`.

    Additional criteria can be passed when using the ``--all-time`` flag. See :class:`~patcher.client.analyze.TrendCriteria`. Trend criteria options are: 

    - ``patch_adoption``: Calculates completion rates over time for different software titles.
    - ``release_frequency``: Analyzes the release frequency of updates for software titles. 
    - ``completion_trends``: Evaluates the correlation between release dates and completion percentages.

- ``top_n`` (:py:class:`int`):
    Number of top entries to display based on the criteria. Default is ``None``, meaning all results will be returned.

- ``summary`` (:py:class:`bool`):
    If passed, will generate a summary file in ``.html`` format in addition to showing results in stdout.

    .. note::

        The ``--summary`` option requires an output directory specified via ``--output-dir``. Ensure the directory exists and has write permissions before running the command. Otherwise, the summary file will not be generated.

- ``output_dir`` (:py:obj:`~typing.Union` [:py:class:`str` | :py:obj:`~pathlib.Path`]):
    Directory to save generated summary if ``--summary`` flag is passed. HTML report will follow a similar naming scheme to exported reports (i.e., ``patch-analysis-<current-date>.html``).

Criteria
^^^^^^^^

Two types of criteria can be specified when leveraging the ``analyze`` command, however they are used in different contexts.

- :class:`~patcher.client.analyze.FilterCriteria` is used when analyzing a **single** patch report.
- :class:`~patcher.client.analyze.TrendCriteria` is used when analyzing patch reports over time.

.. note::

    Both criteria classes automatically handle formatting arguments to the CLI. For example, when analyzing for most installed software titles, ``--criteria most-installed`` is automatically converted to ``most_installed`` at runtime.

Filter Criteria Options
~~~~~~~~~~~~~~~~~~~~~~~

.. container:: sd-table

    .. list-table::
        :header-rows: 1
        :widths: auto

        * - Criteria
          - Description
        * - ``most-installed``
          - Displays software titles with the highest number of total installations.
        * - ``least-installed``
          - Shows the top 5 least-installed software titles. Use ``--top-n`` to limit results.
        * - ``oldest-least-complete``
          - Returns the oldest patches with the least completion percent.
        * - ``below-threshold``
          - Filters software titles with completion percentage below specified ``threshold``.
        * - ``recent-release``
          - Filters for patches released in the last week.
        * - ``zero-completion``
          - Displays software titles with 0% completion.
        * - ``top-performers``
          - Lists software titles with completion percentage above 90%.
        * - ``high-missing``
          - Filters software titles where missing patches are greater than 50% of total hosts.
        * - ``installomator``
          - Returns ``PatchTitles`` that have `Installomator <https://github.com/Installomator/Installomator>`_ labels. Helpful to identify which software titles support automated patching.

Trend Criteria Options
~~~~~~~~~~~~~~~~~~~~~~

.. container:: sd-table

    .. list-table::
        :header-rows: 1
        :widths: auto

        * - Criteria
          - Description
        * - ``patch-adoption``
          - Calculates completion rates over time for different software titles.
        * - ``release-frequency``
          - Analyzes the release frequency of updates for software titles.
        * - ``completion-trends``
          - Evaluates the correlation between release dates and completion percentages.

Usage
-----

.. note::

    Providing an Excel file to the ``analyze`` command is *optional*. In the usage examples below, optional paths are indicated by square brackets.

Filter Criteria
^^^^^^^^^^^^^^^

.. card:: Analyze with Threshold

    .. code-block:: console

        $ patcherctl analyze [/path/to/excel.xlsx] --criteria below-threshold --threshold 50.0

.. card:: Analyze Most Installed

    .. code-block:: console

        $ patcherctl analyze [/path/to/excel.xlsx] --criteria most-installed

.. card:: Analyze Least Installed

    .. code-block:: console

        $ patcherctl analyze [/path/to/excel.xlsx] --criteria least-installed --top-n 5

.. card:: Analyze Recent Releases

    .. code-block:: console

        $ patcherctl analyze [/path/to/excel.xlsx] --criteria recent-release

    .. tip::
        :class: success

        Additionally, option is particularly useful for organizations with Service Level Agreements (SLAs) or policies that mandate installing new patches within a specific time frame (e.g., within 7 days of release).

.. card:: Analyze Zero Completion

    .. code-block:: console

        $ patcherctl analyze [/path/to/excel.xlsx] --criteria zero-completion

.. card:: Analyze High Missing

    .. code-block:: console

        $ patcherctl analyze [/path/to/excel.xlsx] --criteria high-missing --top-n 10

.. card:: Oldest Least Complete

    .. code-block:: console

        $ patcherctl analyze [/path/to/excel.xlsx] --criteria oldest-least-complete

.. card:: Top Performers

    .. code-block:: console

        $ patcherctl analyze [/path/to/excel.xlsx] --criteria top-performers

.. card:: Installomator

    .. code-block:: console

        $ patcherctl analyze [/path/to/excel.xlsx] --criteria installomator

Trend Criteria
^^^^^^^^^^^^^^

.. card:: Patch Adoption

    .. code-block:: console

        $ patcherctl analyze --criteria patch-adoption

.. card:: Release Frequency

    .. code-block:: console

        $ patcherctl analyze --criteria release-frequency

.. card:: Completion Trends

    .. code-block:: console

        $ patcherctl analyze --criteria completion-trends
