.. _property_list_file:

===========================
Property List Configuration
===========================

Patcher uses a property list (``.plist``) file to store persistent settings, such as user interface customizations, setup status, and integration preferences. This file is stored in the Patcher folder of the Application Support directory in the user library: 

``~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist``

.. _v2_format_change:

Property List Format
--------------------

.. admonition:: Changed in version 2.1.1
    :class: warning

    The property list format has been updated to be more simplified, aiming to help end-users interact or modify the settings in a more efficient manner. Below is a summary of the changes. 

.. container:: sd-table

    .. list-table::
        :header-rows: 1
        :widths: auto

        * - Setting
          - Old Key
          - New Key
        * - UI settings
          - ``UI``
          - ``UserInterfaceSettings``
        * - Header text
          - ``HEADER_TEXT``
          - ``header_text``
        * - Footer text
          - ``FOOTER_TEXT``
          - ``footer_text``
        * - Font name
          - ``FONT_NAME``
          - ``font_name``
        * - Regular font location
          - ``FONT_REGULAR_PATH``
          - ``reg_font_path``
        * - Bold font location
          - ``FONT_BOLD_PATH``
          - ``bold_font_path``
        * - Company logo
          - ``LOGO_PATH``
          - ``logo_path``
        * - Setup completion
          - ``first_run_done``
          - ``setup_completed``
        * - Installomator support (:ref:`ref <installomator_support>`)
          - *N/A* 
          - ``enable_installomator``

The new format introduces consistent naming conventions and moves the setup completion flag (``setup_completed``) to a top-level key-value pair rather than being nested under the ``Setup`` dictionary. Additionally, the user interface settings dictionary has been renamed from ``UI`` to ``UserInterfaceSettings`` to improve clarity and maintain consistency. 

Automatic Conversion
^^^^^^^^^^^^^^^^^^^^

For existing users, Patcher will **automatically migrate to the new format** if the previous format is detected. A backup file is also created in the event the migration fails so settings can be revived if necessary. 

.. literalinclude:: ../../src/patcher/client/plist_manager.py
    :lines: 93-127
    :language: python

For a full example of the new format, see the :ref:`XML configuration <full_example_config>` at the bottom of this page.

.. _modify_plist:

Modifying the Property List
---------------------------

The property list can be modified using ``PlistBuddy`` or a code editor of your choice (VSCode, BBEdit, CodeRunner, etc.). The ``defaults`` command can also be leveraged, but is not recommended as it has trouble updating keys nested within dictionaries. 

.. admonition:: Editing Binary Property Lists
    :class: admonition-optional

    By default, property list files are stored in binary format, which text editors cannot modify directly. If you are planning to make changes in an IDE like VSCode or BBEdit, convert the file to XML format first:

    .. code-block:: console

        $ plutil -convert xml1 ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
    
    Once finished making modifications, convert it back to binary format: 

    .. code-block:: console

        $ plutil -convert binary1 ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist

Header & Footer Text
^^^^^^^^^^^^^^^^^^^^

To modify the header and footer text using PlistBuddy, use the following commands:

.. code-block:: console

    $ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:header_text 'Your Custom Header Text'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
    $ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:footer_text 'Your Custom Footer Text'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
    $ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:logo_path 'path/to/your/company/logo.png'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist

.. note::
    The footer text will automatically append a ``|`` character followed by the page number to the end of the specified footer text.

Font Customization
^^^^^^^^^^^^^^^^^^

To change the font, update the ``font_name``, ``reg_font_path`` and ``bold_font_path`` values in the ``UserInterfaceSettings`` dictionary.

.. code-block:: console

    $ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:font_name 'Helvetica'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
    $ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:reg_font_path '/path/to/Helvetica-Regular.ttf'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
    $ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:bold_font_path '/path/to/Helvetica-Bold.ttf'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist

Adding a Company Logo
^^^^^^^^^^^^^^^^^^^^^

Patcher allows branding with a company logo. The logo must be in **PNG, JPEG, or a Pillow-supported format**.

To configure a logo: 

.. code-block:: console

    $ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:logo_path '/path/to/logo.png'"

For more details on customizing fonts and adding a company logo, see :ref:`customize_reports`

.. _installomator_support:

Installomator Support
^^^^^^^^^^^^^^^^^^^^^

To disable :ref:`Installomator support <disabling_installomator_support>`:

.. code-block:: console

    $ defaults write ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist enable_installomator -bool false

.. _full_example_config:

Full Example Configuration
--------------------------

Here is an example configuration with all available keys and values:

.. code-block:: xml

    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>UserInterfaceSettings</key>
        <dict>
            <key>header_text</key>
            <string>AnyOrg Patch Report</string>
            <key>footer_text</key>
            <string>Made with &lt;3 from IT</string>
            <key>font_name</key>
            <string>Assistant</string>
            <key>reg_font_path</key>
            <string>/Users/spesh/Library/Application Support/Patcher/fonts/Assistant-Regular.ttf</string>
            <key>bold_font_path</key>
            <string>/Users/spesh/Library/Application Support/Patcher/fonts/Assistant-Bold.ttf</string>
            <key>logo_path</key>
            <string>/Users/spesh/Library/Application Support/Patcher/logo.png</string>
        </dict>
        <key>setup_completed</key>
        <true/>
        <key>enable_installomator</key>
        <true/>
    </dict>
    </plist>