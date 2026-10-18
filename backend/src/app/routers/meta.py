"""User-defined profile names (file-backed, not CCU)."""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas import ProfileNameBody
from app.services import change_history, profile_names

log = logging.getLogger(__name__)

router = APIRouter(prefix="/profile-names", tags=["profile-names"])


@router.get("")
def get_profile_names() -> dict:
    """Global label per profile slot: {"1": "Standard", ...}."""
    return profile_names.load()


@router.put("/{profile}")
def set_profile_name(profile: int, body: ProfileNameBody) -> dict:
    before = profile_names.load().get(str(profile))
    profile_names.set_name(profile, body.name)
    if before != body.name:
        try:
            change_history.record_name(
                profile, before, f"Name P{profile}: „{before or f'P{profile}'}“ → „{body.name}“"
            )
        except Exception:
            log.warning("rename of P%s not recorded in the change history", profile,
                        exc_info=True)
    return {"profile": profile, "name": body.name}
