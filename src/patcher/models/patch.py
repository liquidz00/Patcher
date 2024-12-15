from pydantic import model_validator

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
    :ivar latest_version: The latest version available for the software title.
    :type latest_version: str
    :ivar completion_percent: The percentage of hosts that have applied the patch.
    :type completion_percent: float
    :ivar total_hosts: The total number of hosts.
    :type total_hosts: int
    """

    title: str
    released: str
    hosts_patched: int
    missing_patch: int
    latest_version: str
    completion_percent: float = 0.0
    total_hosts: int = 0

    # Calculate completion percent via model validator
    @model_validator(mode="after")
    def calculate_completion_percent(self):
        """
        Calculates the completion percentage and total hosts of a :class:`~patcher.models.patch.PatchTitle` object based on hosts_patched and missing_patch.

        See :meth:`~patcher.clients.api_client.ApiClient.get_summaries`
        """
        # Calculate total hosts
        self.total_hosts = self.hosts_patched + self.missing_patch

        # Calculate completion percent
        if self.total_hosts > 0:
            self.completion_percent = round((self.hosts_patched / self.total_hosts) * 100, 2)
        else:
            self.completion_percent = 0.0

        return self
