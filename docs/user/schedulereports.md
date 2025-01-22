(launch_agent)=

# Scheduling Reports

Patcher can be streamlined to schedule the export of patch management reports. This page outlines how to use the provided LaunchAgent to automate the process. While entirely optional, the LaunchAgent offers a convenient method to ensure consistent and timely report generation. 

:::{dropdown} LaunchAgent refresher
:animate: fade-in-slide-down
:icon: bookmark
:color: secondary

A LaunchAgent is a macOS service configuration file used to run tasks on behalf of logged-in users. It's part of the ``launchd`` system and is ideal for scheduling recurring actions like report exports. 
:::

## Purpose of the LaunchAgent

The included LaunchAgent is configured to:

- Automatically generate patch management reports on a scheduled basis. 
- Save these reports in your specified directory in PDF format. 
- Log errors and outputs to help with debugging (if needed). 

Using this LaunchAgent eliminates the need for manual report exports, helping you maintain a consistent reporting schedule.

```{warning}
Ensure that the Python executable and the CLI are on your system's ``PATH``. When installing the project via PyPI, Patcher is typically placed in the ``bin`` directory of your Python installation. If these directories are not in your ``PATH``, Patcher may not work as expected. See {ref}`Adding to PATH <add-path>`
```

## Setting Up the LaunchAgent

Follow these steps to deploy and configure the LaunchAgent:

### 1. Modify the `.plist` File

Customize the provided ``.plist`` file to suit your needs. Key fields to update include: 

- **``ProgramArguments``**: Adjust the boilerplate options in the ``patcherctl export`` command with your desired path or options. See {ref}`Export <export>` command page for more.
- **``StartCalendarInterval``**: Define the schedule for your task. [Launched](https://launched.zerowidth.com/) is an amazing resource for this.

:::{admonition} Optional
:class: admonition-optional

Update the ``StandardErrorPath`` and ``StandardOutPath`` strings if you would like LaunchAgent logs to go to a different directory.
:::

#### Example ``.plist`` Configuration

The example below schedules the task to run on the first day of each month at 9:00 AM:

```{code-block} xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.liquidzoo.patcher-export.plist</string>
    <key>ProgramArguments</key>
    <array>
      <string>sh</string>
      <string>-c</string>
      <string>patcherctl export --path /path/to/save --pdf</string>
    </array>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Application\ Support/Patcher/logs/patcher-agent.err.log</string>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Application\ Support/Patcher/logs/patcher-agent.out.log</string>
    <key>StartCalendarInterval</key>
    <array>
      <dict>
        <key>Day</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
      </dict>
    </array>
  </dict>
</plist>
```

### 2. Deploy the ``.plist`` File

Place the modified ``.plist`` file in the ``~/Library/LaunchAgents/`` directory: 

```{code-block} bash
$ cp com.liquidzoo.patcher-export.plist ~/Library/LaunchAgents/
```

Ensure the LaunchAgent has the proper permissions: 

```{code-block} bash
$ chmod 644 ~/Library/LaunchAgents/com.liquidzoo.patcher-export.plist
```

Load the LaunchAgent:

```{code-block} bash
$ launchctl load ~/Library/LaunchAgents/com.liquidzoo.patcher-export.plist
```

To verify the LaunchAgent is active:

```{code-block} bash
$ launchctl list | grep com.liquidzoo.patcher-export
```

### Testing the Configuration 

To ensure the LaunchAgent is working: 

1. Manually run the ``patcherctl export`` command to confirm it executes as expected. 
2. Check the logs for errors or confirmation of success:
   - **Standard Output**: ``~/Library/Application Support/Patcher/logs/patcher-agent.out.log``
   - **Standard Error**: ``~/Library/Application Support/Patcher/logs/patcher-agent.err.log``

### Troubleshooting

If the LaunchAgent does not work as expected: 

- Verify the ``.plist`` file is correctly placed and formatted. 
- Ensure file permissions are properly set. 
- Review the logs for detailed error messages: 

```{code-block} bash
$ tail -f ~/Library/Application\ Support/Patcher/logs/patcher-agent.err.log
```

