"""Runtime dataclass grouping core dependencies initialised by build_runtime()."""

from __future__ import annotations

from dataclasses import dataclass

from model_bridge.adapters.base import BaseAdapter
from model_bridge.core.failover_manager import FailoverManager
from model_bridge.security.sanitizer import SecuritySanitizer


@dataclass
class Runtime:
    """Immutable-ish bag of the four objects produced by build_runtime().

    Fields may be mutated in-place (e.g. by ``set_config``), but the
    dataclass itself is never replaced once stored in the module-level
    ``_RUNTIME`` variable.
    """

    config: dict
    adapter: BaseAdapter
    failover: FailoverManager
    sanitizer: SecuritySanitizer
