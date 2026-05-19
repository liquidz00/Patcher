---
description: "Frequently asked questions about Patcher: name origin, license, supported Jamf APIs, deployment patterns, and other quick answers."
---

(faq)=

# Frequently Asked Questions

:::{rst-class} lead
Quick answers to the questions that come up most.
:::

::::{grid} auto
:class-container: sd-text-left
:gutter: 2
:margin: 2

:::{grid-item-card} {fas}`question;sd-text-secondary`  Why `patcherctl`?
:class-card: sd-card
:shadow: md

The package (and binary) is called `patcherctl` because the name `patcher` was already taken on PyPI. The project itself is still referred to as Patcher.
:::

:::{grid-item-card} {fas}`question;sd-text-secondary`  Does Patcher work on Windows?
:class-card: sd-card
:shadow: md

Not currently. Patcher is designed for MacAdmins and assumes macOS conventions (keychain, Application Support directory, `defaults`/`PlistBuddy`). Running inside a Docker container has been considered and may be pursued further.
:::

:::{grid-item-card} {fas}`question;sd-text-secondary`  What are the system requirements?
:class-card: sd-card
:shadow: md

macOS 13 (Ventura) or higher. Patcher may work on earlier versions but hasn't been tested there.

For Jamf Pro system requirements, see the [Jamf Pro Documentation](https://learn.jamf.com/en-US/bundle/jamf-pro-documentation-current/page/System_Requirements.html).
:::

:::{grid-item-card} {fas}`question;sd-text-secondary`  How do I report a bug or contribute?
:class-card: sd-card
:shadow: md

All contribution types are welcome: bug reports, feature requests, code, docs. See the {ref}`Contributing <contributing_index>` page for details.

For quick questions, find us on the MacAdmins Slack: [#patcher](https://macadmins.slack.com/archives/C07EH1R7LB0).
:::

:::{grid-item-card} {fas}`question;sd-text-secondary`  Does Patcher support multiple Jamf Pro environments?
:class-card: sd-card
:shadow: md

Partially. Patcher can be reset and pointed at a different Jamf URL, but it's only been tested against a single Jamf instance using two [sites](https://learn.jamf.com/en-US/bundle/jamf-pro-documentation-current/page/Sites.html), so multi-instance is unverified.
:::

:::{grid-item-card} {fas}`question;sd-text-secondary`  Where are logs stored?
:class-card: sd-card
:shadow: md

All CLI logs go to `~/Library/Application Support/Patcher/logs`. If you're using the {ref}`LaunchAgent <launch_agent>` for scheduled exports, its stdout / stderr also land there.

For more on parsing what's in the logs, see {ref}`Interpreting Patcher Logs <logs>`.
:::

:::{grid-item-card} {fas}`question;sd-text-secondary`  How does Patcher handle TLS in corporate environments?
:class-card: sd-card
:shadow: md

Patcher uses `httpx` configured with [`truststore`](https://github.com/sethmlarson/truststore), so TLS verification queries your **operating system's** trust store directly (macOS Keychain). Any CA your MDM pushes is automatically trusted. No `certifi` edits, no `SSL_CERT_FILE`, no Python-specific configuration.

This means TLS-inspecting proxies (Zscaler, Netskope, Cloudflare Gateway, Palo Alto GlobalProtect) work transparently in most environments. If you still hit certificate errors, see {ref}`TLS / Corporate Proxies <support>`.
:::

::::
