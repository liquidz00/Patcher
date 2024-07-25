.. _customize_reports:

=====================
Customize PDF Reports
=====================

Tailor the user interface elements of your exported PDF reports. You have the flexibility to modify the font, and customize the header and footer text according to your preferences. See the sample PDF image below for an illustration of these customizable features.

.. _example-pdf-image:

.. image:: images/example_pdf.jpeg
    :alt: Example PDF
    :width: 750px
    :align: center

.. seealso::
    Configuring the date format is done at runtime by using the ``--date-format`` option. See :ref:`date format <date-format>` for more information.

Setup
-----

When you first launch Patcher, a :ref:`setup assistant <setup-assistant>` will automatically create the necessary ``config.ini`` file and copy the required fonts to the appropriate directory.

Modifying the file
^^^^^^^^^^^^^^^^^^

Any resource Patcher interacts with can be found in the Application Support directory in the user library. Using ``jappleseed`` as an example, the path to the configuration file would be ``'/Users/jappleseed/Library/Application Support/Patcher/config.ini'``.

Open this file in your text editor of choice, or execute the command below in Terminal to open the file in the TextEdit app.

.. code-block:: console

    open -a "TextEdit.app" ~/Library/Application\ Support/Patcher/config.ini

Sample configuration
^^^^^^^^^^^^^^^^^^^^

**Still assuming the logged in user is jappleseed**, a ``config.ini`` file could look like the following:

.. code-block:: ini

    [Settings]
    patcher_path = /Users/jappleseed/Library/Application Support/Patcher

    [UI]
    header_text = AnyOrg Mac Patch Report
    footer_text = AnyOrg Mac Patch Report
    font_name = Assistant
    font_regular_path = /Users/jappleseed/Library/Application Support/Patcher/fonts/Assistant-Regular.ttf
    font_bold_path = /Users/jappleseed/Library/Application Support/Patcher/fonts/Assistant-Bold.ttf

The above example would result in a PDF report that looks identical to the :ref:`example PDF image <example-pdf-image` at the top of this page.

.. warning::
    Altering the ``[Settings]`` section of the configuration file is not recommended. Patcher references this path throughout the codebase and modifying it incorrectly may lead to unintended results or errors.

Edit Header and Footer Text
---------------------------

To customize the header and footer texts, simply modify the ``header_text`` and ``footer_text`` values under the UI section of the config file.

.. code-block:: ini

    [UI]
    header_text = Your Custom Header Text
    footer_text = Your Custom Footer Text

.. note::
    The footer text will automatically append a ``|`` character followed by the page number to the end of the specified footer text.

Customizing the Font
--------------------

If you wish to change the font, modify the ``font_name``, ``font_regular_path`` and ``font_bold_path`` values in the UI section:

.. code-block:: ini

   [UI]
   font_name = YourPreferredFont
   font_regular_path = /path/to/your/font/Regular.ttf
   font_bold_path = /path/to/your/font/Bold.ttf

.. important::
    The default font used in testing is `Google's Assistant Font <https://fonts.google.com/specimen/Assistant>`_. While you can specify a different font to match your organization's branding, be aware that doing so may cause formatting or alignment issues in the exported PDF reports. It is recommended to test the PDF export functionality thoroughly after changing the font to ensure the new font does not adversely affect the document's appearance.

Full Example Configuration
--------------------------

A full example configuration with custom header, footer text and a specified font:

.. code-block:: ini

   [Settings]
   patcher_path = /Users/$user/Library/Application Support/Patcher

   [UI]
   header_text = Confidential Report
   footer_text = © 2024 Your Company
   font_name = Helvetica
   font_regular_path = /path/to/Helvetica-Regular.ttf
   font_bold_path = /path/to/Helvetica-Bold.ttf
