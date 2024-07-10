from typing import AnyStr, List, Optional

from .. import logger
from . import Model

logthis = logger.setup_child_logger("PatchTitle", __name__)


class PatchTitle(Model):
    title: AnyStr
    released: AnyStr
    hosts_patched: int
    missing_patch: int
    completion_percent: float
    total_hosts: int
    applicable_cves: Optional[List[str]] = None
    installomator: Optional[str] = None
