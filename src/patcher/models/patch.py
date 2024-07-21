from typing import AnyStr

from . import Model


class PatchTitle(Model):
    """
    Represents patch software title information retrieved via API calls.

    :ivar title: The name of the patch title.
    :type title: AnyStr
    :ivar released: The release date of the patch title.
    :type released: AnyStr
    :ivar hosts_patched: The number of hosts that have applied the patch.
    :type hosts_patched: int
    :ivar missing_patch: The number of hosts missing the patch.
    :type missing_patch: int
    :ivar completion_percent: The percentage of hosts that have applied the patch.
    :type completion_percent: float
    :ivar total_hosts: The total number of hosts.
    :type total_hosts: int

    Attributes:
        title (AnyStr): The name of the patch title.
        released (AnyStr): The release date of the patch title.
        hosts_patched (int): The number of hosts that have applied the patch.
        missing_patch (int): The number of hosts missing the patch.
        completion_percent (float): The percentage of hosts that have applied the patch.
        total_hosts (int): The total number of hosts.
    """
    title: AnyStr
    released: AnyStr
    hosts_patched: int
    missing_patch: int
    completion_percent: float
    total_hosts: int
