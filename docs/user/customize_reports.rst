.. _customize_reports:

====================
Customizing Reports
====================

Tailor the user interface elements of your exported PDF reports. You have the flexibility to modify the font, customize the header and footer text, and provide a company logo according to your preferences. See the sample PDF image below for an illustration of these customizable features.

.. _example-pdf-image:

.. image:: ../_static/example_pdf.png
    :alt: Example PDF
    :width: 750px
    :align: center

.. seealso::
    Configuring the date format is done at runtime by using the ``--date-format`` option. See :ref:`date format <date-format>` for more information.


Customizable User Interface Elements
------------------------------------

Patcher allow syou to personalize the appearance of your reports using settings stored in the project's property list file. For full details on modifying the property list, see :ref:`Property List Configuration <property_list_file>`.

Editing the Header & Footer Text
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The header and footer text displayed in exported reports can be adjusted. These settings are stored in the ``com.liquidzoo.patcher.plist`` file under the ``UserInterfaceSettings`` dictionary. 

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
        </dict>
    </dict>
    </plist>


Customizing the Font
^^^^^^^^^^^^^^^^^^^^

You can specify a custom font to match your organization's branding. The font settings, including font name and paths to font files are stored in the property list.

.. important::
    The default font used in testing is `Google's Assistant Font <https://fonts.google.com/specimen/Assistant>`_. While you can specify a different font to match your organization's branding, be aware that doing so may cause formatting or alignment issues in the exported PDF reports. It is recommended to test the PDF export functionality thoroughly after changing the font to ensure the new font does not adversely affect the document's appearance.

.. code-block:: xml

    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>UserInterfaceSettings</key>
        <dict>
            <key>font_name</key>
            <string>Assistant</string>
            <key>reg_font_path</key>
            <string>/Users/spesh/Library/Application Support/Patcher/fonts/Assistant-Regular.ttf</string>
            <key>bold_font_path</key>
            <string>/Users/spesh/Library/Application Support/Patcher/fonts/Assistant-Bold.ttf</string>
        </dict>
    </dict>
    </plist>

.. _customize_logo:

Adding a Company Logo
---------------------

.. admonition:: Added in version 2.0
    :class: tip

    Patcher allows you to include a company logo in your exported PDF reports. This can be helpful for ensuring unified branding for reports.

Supported Logo Requirements
^^^^^^^^^^^^^^^^^^^^^^^^^^^

- **File Formats**: The logo must be a valid image file in PNG, JPEG, or other `Pillow-supported formats <https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#fully-supported-formats>`_
- **File Validation**: Patcher will validate the logo to ensure it is a valid image file before being added to the report. 

.. seealso::
    Need to make your own logo file? The `macOS-icon-generator <https://github.com/SAP/macOS-icon-generator>`_ by SAP is a great (and free) resource for creating standardized app icons in PNG format.  

Configuring a Logo
^^^^^^^^^^^^^^^^^^

There are two primary methods to configure a logo for your PDF reports: 

1. Resetting existing UI configuration via the :ref:`reset <reset>` command. 
2. Modifying the property list by passing the logo file to the corresponding key.

Via ``reset``:
~~~~~~~~~~~~~~

1. Execute the ``reset`` command:

.. code-block:: console
    
    $ patcherctl reset ui

2. After providing values for header/footer text and custom font, you will be prompted to use a custom logo with the question ``Would you like to use a logo in your exported PDFs?``
3. Enter the file path to your desired logo image when prompted: 

.. code-block:: console
    
    $ Enter the path to the logo file: /path/to/logo.png

4. Patcher will validate the image file. If valid, it will copy the logo to the ``Application Support`` directory: ``$HOME/Library/Application Support/Patcher/logo.png``
5. The logo path is then saved to the ``com.liquidzoo.patcher.plist`` file under the ``UserInterface`` dictionary:

.. code-block:: xml
    
    <key>logo_path</key>
    <string>/Users/jappleseed/Library/Application Support/Patcher/logo.png</string>

Via the property list:
~~~~~~~~~~~~~~~~~~~~~~

Open the property list file in Xcode or use ``PlistBuddy`` to modify the property list file. (See :ref:`Modifying the Property List File <modify_plist>`). For demonstration purposes, ``PlistBuddy`` will be used. 

.. tip::
    Absolute paths can be copied easily in macOS: Hold down the Option (⌥) symbol on the keyboard, right-click the logo file and select **Copy <filename> as Pathname**

1. Copy the path to your desired logo. 
2. Execute the following command to add the logo file to the property list: 

.. code-block:: console
    
    $ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:logo_path '/path/to/logo.png'" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist

3. While it is not **required** to copy the logo file to Patcher's Application Support directory, it ensures the proper permissions are enabled to read the logo file. 

Example UI Settings Configuration
=================================

Here is an example configuration of **only** the ``UserInterfaceSettings`` dictionary with custom header, footer text, specified font, and custom logo:

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
    </dict>
    </plist>

The above example would result in a PDF report that looks identical to the :ref:`example PDF image <example-pdf-image>` at the top of this page.
