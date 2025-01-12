.. _customize_reports:

====================
Customizing Reports
====================

Tailor the user interface elements of your exported PDF reports. You have the flexibility to modify the font, and customize the header and footer text according to your preferences. See the sample PDF image below for an illustration of these customizable features.

.. _example-pdf-image:

.. image:: ../_static/example_pdf.png
    :alt: Example PDF
    :width: 750px
    :align: center

.. seealso::
    Configuring the date format is done at runtime by using the ``--date-format`` option. See :ref:`date format <date-format>` for more information.

.. _property_list_file:

Setup
=====

When you first launch Patcher, a :ref:`setup assistant <setup>` will automatically create the necessary ``com.liquidzoo.patcher.plist`` file in the user's Library Application Support directory, located at ``$HOME/Library/Application Support/Patcher``. Once setup is completed successfully, the ``first_run_done`` key in the property list file will automatically be set to ``True``:

.. code-block:: xml

    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>Setup</key>
        <dict>
            <key>first_run_done</key>
            <true/>
        </dict>
    </dict>
    </plist>

.. admonition:: Warning
    :class: warning

    **Do not modify** the ``first_run_done`` key in the ``Setup`` dictionary directly. Altering this key may cause Patcher to re-run the setup process. If you need to reset the initial setup state, use the ``--reset`` option instead. For more information, see :ref:`resetting Patcher <resetting_patcher>`.

Modifying the Property List File
================================

The property list file contains the settings that control the appearance of the PDF reports. You can edit these values using ``/usr/libexec/PlistBuddy`` or a code editor of your choice (VSCode, BBEdit, CodeRunner, etc.).

.. admonition:: Opening Property Lists in Xcode
    :class: tip

    If the plist file appears as a binary file when opened in VSCode or other editors, you can open it in **Xcode** instead. Xcode is available as a free download from the Mac App Store and fully supports editing plist files. This will prevent issues with binary formatting that some editors may encounter.

Using ``jappleseed`` as an example, the path to the property list file would be:

``/Users/jappleseed/Library/Application Support/Patcher/com.liquidzoo.patcher.plist``

Editing the Header & Footer Text
--------------------------------

.. tip::
    Why not use ``defaults`` to edit the property list file? Unfortunately, the ``defaults`` binary in macOS lacks the ability to update keys nested within dictionaries. ``PlistBuddy`` is much better equipped to handle property lists with nested elements.

To modify the header and footer text using PlistBuddy, use the following commands:

.. code-block:: console

    $ /usr/libexec/PlistBuddy -c "Set :UI:HEADER_TEXT 'Your Custom Header Text'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
    $ /usr/libexec/PlistBuddy -c "Set :UI:FOOTER_TEXT 'Your Custom Footer Text'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
    $ /usr/libexec/PlistBuddy -c "Set :UI:LOGO_PATH 'path/to/your/company/logo.png'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist

These commands will correctly update the ``HEADER_TEXT``, ``FOOTER_TEXT`` and ``LOGO_PATH`` keys within the ``UI`` dictionary.

.. note::
    The footer text will automatically append a ``|`` character followed by the page number to the end of the specified footer text.

Sample Property List Structure
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Below is an example of what the nested UI dictionary might look like in the property list file:

.. code-block:: xml

    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>UI</key>
        <dict>
            <key>HEADER_TEXT</key>
            <string>AnyOrg Patch Report</string>
            <key>FOOTER_TEXT</key>
            <string>AnyOrg Patch Report</string>
            <key>FONT_NAME</key>
            <string>Assistant</string>
            <key>FONT_REGULAR_PATH</key>
            <string>/Users/jappleseed/Library/Application Support/Patcher/fonts/Assistant-Regular.ttf</string>
            <key>FONT_BOLD_PATH</key>
            <string>/Users/jappleseed/Library/Application Support/Patcher/fonts/Assistant-Bold.ttf</string>
            <key>LOGO_PATH</key>
            <string>/Users/jappleseed/Desktop/AnyOrg.jpg</string>
        </dict>
    </dict>
    </plist>

The above example would result in a PDF report that looks identical to the :ref:`example PDF image <example-pdf-image>` at the top of this page.

Customizing the Font
--------------------

To change the font, update the ``FONT_NAME``, ``FONT_REGULAR_PATH`` and ``FONT_BOLD_PATH`` values in the UI dictionary.

.. code-block:: console

    $ /usr/libexec/PlistBuddy -c "Set :UI:FONT_NAME 'Helvetica'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
    $ /usr/libexec/PlistBuddy -c "Set :UI:FONT_REGULAR_PATH '/path/to/Helvetica-Regular.ttf'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
    $ /usr/libexec/PlistBuddy -c "Set :UI:FONT_BOLD_PATH '/path/to/Helvetica-Bold.ttf'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist

.. important::
    The default font used in testing is `Google's Assistant Font <https://fonts.google.com/specimen/Assistant>`_. While you can specify a different font to match your organization's branding, be aware that doing so may cause formatting or alignment issues in the exported PDF reports. It is recommended to test the PDF export functionality thoroughly after changing the font to ensure the new font does not adversely affect the document's appearance.

Full Example Configuration
--------------------------

Here is an example configuration with custom header, footer text, and a specified font:

.. code-block:: xml

    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>Setup</key>
        <dict>
            <key>first_run_done</key>
            <true/>
        </dict>
        <key>UI</key>
        <dict>
            <key>HEADER_TEXT</key>
            <string>Confidential Report</string>
            <key>FOOTER_TEXT</key>
            <string>© 2024 Your Company</string>
            <key>FONT_NAME</key>
            <string>Helvetica</string>
            <key>FONT_REGULAR_PATH</key>
            <string>/path/to/Helvetica-Regular.ttf</string>
            <key>FONT_BOLD_PATH</key>
            <string>/path/to/Helvetica-Bold.ttf</string>
            <key>LOGO_PATH</key>
            <string>/Users/jappleseed/Desktop/AnyOrg.jpg</string>
        </dict>
    </dict>
    </plist>
