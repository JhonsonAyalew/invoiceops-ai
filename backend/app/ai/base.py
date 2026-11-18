"""Provider-independent AI interface. Extraction code only ever sees AIProvider."""

from __future__ import annotations

from abc import ABC, abstractmethod


class AIError(Exception):
    pass


class AIUnavailable(AIError):
    """Provider not configured / unreachable."""


class ConsentRequired(AIError):
    """Cloud provider used without explicit operator authorization."""


class AIProvider(ABC):
    name: str = "base"
    is_cloud: bool = False  # True => document text leaves this machine

    @abstractmethod
    def complete_json(self, system: str, user: str) -> str:
        """Return the model's raw text reply (expected to be a JSON object)."""

    def health(self) -> dict:
        return {"provider": self.name, "cloud": self.is_cloud, "configured": True}
