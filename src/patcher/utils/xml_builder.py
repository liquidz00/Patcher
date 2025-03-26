from typing import Dict, Literal, Optional
from xml.etree import ElementTree as ET

from ..client.plist_manager import PropertyListManager
from .exceptions import PatcherError


class XMLBuilder:
    def __init__(
        self,
        site_id: int = -1,
        site_name: str = "NONE",
        plist_manager: Optional[PropertyListManager] = None,
    ):
        self.site_id = str(site_id)
        self.site_name = site_name
        self.plist_manager = plist_manager or PropertyListManager()

    def _add(self, parent: ET.Element, tag: str, text: Optional[str] = None) -> ET.SubElement:
        """Helper function to dynamically add nodes to parent element."""
        elem = ET.SubElement(parent, tag)
        if text is not None:
            elem.text = str(text)
        return elem

    def _build_computer_group(self, app_name: str, type: Literal["has", "latest"]) -> ET.Element:
        """Builds the ``computer_group`` portion of smart group payload."""
        if type not in ("has", "latest"):
            raise PatcherError("Received unsupported smart group type.", received=type)

        computer_group = ET.Element("computer_group")

        self._add(
            computer_group, "name", f"{'Has' if type == 'has' else 'Latest Version'} - {app_name}"
        )
        self._add(computer_group, "is_smart", "true")
        site = self._add(computer_group, "site")
        self._add(site, "id", self.site_id)
        self._add(site, "name", self.site_name)

        return computer_group

    def _build_criteria(self, app_name: str, type: Literal["has", "latest"]) -> ET.Element:
        """Builds the ``criteria`` portion of smart group payload."""
        criteria = ET.Element("criteria")
        self._add(criteria, "size", "1")
        criterion = self._add(criteria, "criterion")
        self._add(
            criterion,
            "name",
            ("Application Title" if type == "has" else f"Patch Reporting: {app_name}"),
        )
        criterion_data = {
            "priority": "0",
            "and_or": "and",
            "search_type": "has" if type == "has" else "is",
            "value": f"{app_name}.app" if type == "has" else "Latest Version",
            "opening_paren": "false",
            "closing_paren": "false",
        }
        for k, v in criterion_data.items():
            self._add(criterion, k, v)

        return criteria

    def _build_general(self, app_name: str) -> ET.Element:
        """Builds the ``general`` portion of policy payloads."""
        default = {
            "enabled": "true",
            "trigger": "CHECKIN",
            "trigger_checkin": "true",
            "frequency": "Once every day",
        }
        general = ET.Element("general")
        self._add(general, "name", f"Patch Management - {app_name}")
        for k, v in default.items():
            self._add(general, k, v)
        return general

    def _build_scope(self, sg_has: Dict, sg_latest: Dict) -> ET.Element:
        """Builds the ``scope`` portion of policy payloads."""
        scope = ET.Element("scope")
        self._add(scope, "all_computers", "false")

        # targets
        targets = self._add(scope, "computer_groups")
        group = self._add(targets, "computer_group")
        self._add(group, "id", sg_has.get("id"))
        self._add(group, "name", sg_has.get("name"))

        # exclusions
        exclusions = self._add(scope, "exclusions")
        exclude_groups = self._add(exclusions, "computer_groups")
        exclude_group = self._add(exclude_groups, "computer_group")
        self._add(exclude_group, "id", sg_latest.get("id"))
        self._add(exclude_group, "name", sg_latest.get("name"))

        return scope

    def _build_scripts(
        self, script_id: int, script_name: str, installomator_label: str, parameters: Dict
    ) -> ET.Element:
        """Builds the ``scripts`` portion of policy payloads."""
        default = {
            "id": script_id,
            "name": script_name,
            "priority": "After",
            "parameter4": installomator_label,
        }
        scripts = ET.Element("scripts")
        self._add(scripts, "size", "1")
        script = self._add(scripts, "script")
        for k, v in default.items():
            self._add(script, k, v)

        for i in range(5, 12):
            key = f"parameter{i}"
            self._add(script, key, parameters.get(key, ""))

        return scripts

    def _build_maintenance(self) -> ET.Element:
        """Builds the ``maintenance`` portion of policy payloads."""
        maint = ET.Element("maintenance")
        self._add(maint, "recon", "true")
        return maint

    def generate_smart_group(self, app_name: str, type: Literal["has", "latest"]) -> str:
        """
        Creates XML payload to create Smart Computer Groups in Jamf.

        :param app_name: Name of the Application to set the smart groups up for.
        :type app_name: :py:class:`str`
        :param type: The type of smart group to create. ``"has"`` to create smart group for hosts that have application installed, or ``"latest"`` to denote hosts running latest version of application.
        :type type: :py:obj:`~typing.Literal`
        :return: The formatted XML payload as a string.
        :rtype: :py:class:`str`
        """
        root = self._build_computer_group(app_name, type)
        root.append(self._build_criteria(app_name, type))
        return ET.tostring(root, encoding="unicode")

    def generate_policy(
        self,
        app_name: str,
        script_id: int,
        script_name: str,
        sg_has: Dict,
        sg_latest: Dict,
        installomator_label: str,
        parameters: Dict,
    ) -> str:
        """
        Creates XML payload to create a Jamf Policy leveraging Installomator.

        :param app_name: The name of the application to patch.
        :type app_name: :py:class:`str`
        :param script_id: The Jamf Pro script ID of the Installomator.sh script.
        :type script_id: :py:class:`int`
        :param script_name: The name of the script to reference in policy payload.
        :type script_name: :py:class:`str`
        :param sg_has: Dictionary of metadata for the Smart Group scoped to hosts that have the application.
        :type sg_has: :py:obj:`~typing.Dict`
        :param sg_latest: Dictionary of metadata for the Smart Group scoped to hosts that are up-to-date.
        :type sg_latest: :py:obj:`~typing.Dict`
        :param installomator_label: The installomator label to pass to the script.
        :type installomator_label: :py:class:`str`
        :param parameters: Dictionary containing any Installomator parameters (5-11) to include.
        :type parameters: :py:obj:`~typing.Dict`
        :return: The formatted XML payload as a string.
        :rtype: :py:class:`str`
        """
        root = ET.Element("policy")
        root.append(self._build_general(app_name))
        root.append(self._build_scope(sg_has, sg_latest))
        root.append(self._build_scripts(script_id, script_name, installomator_label, parameters))
        root.append(self._build_maintenance())
        return ET.tostring(root, encoding="unicode")

    def generate_category(self, category_name: Optional[str] = "Patch Management") -> str:
        """
        Creates XML payload to create a new Jamf Category.

        :param category_name: The name of the Jamf Category to create. Defaults to "Patch Management".
        :type category_name: :py:obj:`~typing.Optional` [:py:class:`str`]
        :return: The formatted XML payload as a string.
        :rtype: :py:class:`str`
        """
        category = ET.Element("category")
        self._add(category, "name", category_name)
        return ET.tostring(category, encoding="unicode")
