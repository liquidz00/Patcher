.. _setup:

=====
Setup
=====

Our aim as developers of this tool is to streamline the setup and installation process to be as straightforward as possible. We understand there's nothing more frustrating than the anticipation of using a new tool, only to be bogged down by extensive configuration or setup steps before you can even start. To address this, we introduced a setup assistant in version ``1.3.2`` (and up) that automates the initial configuration. This page will demonstrate how the tool operates under the hood, giving you the end-user insight into how to trigger it again if necessary.

First Run Detection
-------------------

Patcher needs to know whether it is being run for the first time. This is important so that credentials are saved and stored properly and `user-interface customizations <https://github.com/liquidz00/Patcher/wiki/Customizing-PDF-Reports>`_ are setup for subsequent uses. Here is how the process works:

1. **First Run Check**: When Patcher is executed, it looks for a property list in Patcher's Application Support directory. Specifically, it checks for the presence of ``com.liquidzoo.patcher.plist`` in ``/Users/$username/Library/Application Support/Patcher``, where ``$username`` denotes the currently logged in user.
2. **Key Check**: If the property list is found, Patcher will parse its contents for the ``first_run_done`` key.
    - If the file does not exist, or if the key is set to ``False``, the setup assistant is triggered.
    - The key *must* be set to ``True`` to prevent the setup assistant from running.

Reference
^^^^^^^^^

For more details, refer to the following Patcher documentation:

- The :py:mod:`patcher.client.setup` module for the Setup class sourcecode, which handles the launching of the setup assistant.
- The :ref:`usage` section for information on command line options, specifically the ``--reset`` option.
