from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Optional


class SessionPhase(Enum):
    IDLE = auto()
    LOADING = auto()
    ANNOTATING = auto()
    SAVING = auto()
    SUBMITTING = auto()
    ABOLISHING = auto()
    ERROR = auto()


@dataclass
class WorkspaceSession:

    generation: int = 0

    phase: SessionPhase = SessionPhase.IDLE

    current_metadata: Optional[dict] = None
    pending_metadata: Optional[dict] = None

    dirty: bool = False

    last_submit_metadata: Optional[dict] = None
    last_submit_annotations: Optional[dict] = None

    last_error: Optional[str] = None
    last_saved_at: Optional[datetime] = None

    def new_generation(self) -> int:
        self.generation += 1
        return self.generation
