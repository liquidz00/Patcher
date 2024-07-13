from typing import AnyStr

from ..utils import logger
from . import Model

logthis = logger.setup_child_logger("PatchTitle", __name__)


class PatchTitle(Model):
    title: AnyStr
    released: AnyStr
    hosts_patched: int
    missing_patch: int
    completion_percent: float
    total_hosts: int
