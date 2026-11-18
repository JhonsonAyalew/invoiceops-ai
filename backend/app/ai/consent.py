"""Explicit operator authorization before document text is sent to a cloud provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .base import AIProvider, ConsentRequired


@dataclass(frozen=True)
class CloudConsent:
    """Recorded per job. Created only by an explicit operator action; never defaulted to granted."""

    job_id: str
    provider: str
    granted_at: datetime

    @classmethod
    def grant(cls, job_id: str, provider: str) -> "CloudConsent":
        return cls(job_id, provider, datetime.now(timezone.utc))


def check_consent(provider: AIProvider, job_id: str, consent: CloudConsent | None) -> None:
    """Local providers need no consent. Cloud providers need consent for THIS job and THIS provider."""
    if not provider.is_cloud:
        return
    if consent is None or consent.job_id != job_id or consent.provider != provider.name:
        raise ConsentRequired(f"Sending job {job_id} content to {provider.name} requires explicit operator authorization")
