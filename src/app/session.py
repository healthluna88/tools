from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkspaceSession:

    current_metadata: dict | None = None

    dirty: bool = False
