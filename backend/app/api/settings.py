"""User-adjustable settings (worker count, loudness target), disk usage, and model
presence status. Downloading missing models from an HTTP request handler is out of
scope here — multi-hundred-MB transfers need real progress reporting, which is more
than this small card warrants; the page instead tells the user to run
`python scripts/fetch_models.py`. See PLAN.md.
"""
import shutil

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from .. import settings_store
from ..config import Settings, get_settings
from ..db import get_session
from ..model_manifest import MANIFEST, is_valid

router = APIRouter()


class SettingsOut(BaseModel):
    tts_workers: int
    loudness_target_i: float
    loudness_target_tp: float
    loudness_target_lra: float
    output_dir: str
    models_dir: str


class SettingsUpdate(BaseModel):
    tts_workers: int | None = None
    loudness_target_i: float | None = None
    loudness_target_tp: float | None = None
    loudness_target_lra: float | None = None


class DiskUsageOut(BaseModel):
    cache_bytes: int
    output_bytes: int
    models_bytes: int
    free_bytes: int


class ModelStatusOut(BaseModel):
    dest: str
    size_bytes: int
    present: bool


def _dir_size(path) -> int:
    if not path.is_dir():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


@router.get("/settings", response_model=SettingsOut)
def get_settings_values(session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> SettingsOut:
    typed = settings_store.get_typed(session)
    return SettingsOut(
        **typed,
        output_dir=str(settings.output_dir()),
        models_dir=str(settings.models_dir),
    )


@router.put("/settings", response_model=SettingsOut)
def update_settings_values(
    body: SettingsUpdate, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
) -> SettingsOut:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "tts_workers" in updates and updates["tts_workers"] < 1:
        raise HTTPException(status_code=422, detail="tts_workers must be at least 1")

    settings_store.set_many(session, {k: str(v) for k, v in updates.items()})

    typed = settings_store.get_typed(session)
    return SettingsOut(
        **typed,
        output_dir=str(settings.output_dir()),
        models_dir=str(settings.models_dir),
    )


@router.get("/settings/disk-usage", response_model=DiskUsageOut)
def get_disk_usage(settings: Settings = Depends(get_settings)) -> DiskUsageOut:
    usage = shutil.disk_usage(settings.data_dir)
    return DiskUsageOut(
        cache_bytes=_dir_size(settings.cache_dir()),
        output_bytes=_dir_size(settings.output_dir()),
        models_bytes=_dir_size(settings.models_dir),
        free_bytes=usage.free,
    )


@router.get("/settings/models", response_model=list[ModelStatusOut])
def get_model_status(settings: Settings = Depends(get_settings)) -> list[ModelStatusOut]:
    return [
        ModelStatusOut(
            dest=model.dest, size_bytes=model.size,
            present=is_valid(settings.models_dir / model.dest, model),
        )
        for model in MANIFEST
    ]
