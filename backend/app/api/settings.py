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
    mp4_part_limit_s: float
    output_dir: str
    models_dir: str


class SettingsUpdate(BaseModel):
    tts_workers: int | None = None
    loudness_target_i: float | None = None
    loudness_target_tp: float | None = None
    loudness_target_lra: float | None = None
    mp4_part_limit_s: float | None = None


class DiskUsageOut(BaseModel):
    cache_bytes: int
    output_bytes: int
    models_bytes: int
    free_bytes: int


class ModelStatusOut(BaseModel):
    dest: str
    size_bytes: int
    present: bool


class CachePruneOut(BaseModel):
    files_removed: int
    bytes_freed: int


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
    if "mp4_part_limit_s" in updates and updates["mp4_part_limit_s"] <= 0:
        raise HTTPException(status_code=422, detail="mp4_part_limit_s must be positive")

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


@router.delete("/settings/cache", response_model=CachePruneOut)
def prune_cache(settings: Settings = Depends(get_settings)) -> CachePruneOut:
    """[M6-4]: a manual, explicit "empty the chunk cache" action — every render adds
    content-addressed chunks that never expire on their own, and on a machine with
    little free disk this is the release valve. Safe by design, not just in practice:
    the worker pool already treats a missing cache entry as a plain cache miss and
    re-synthesizes it (pipeline/cache.py), so pruning mid-render costs redundant work
    at worst, never a crash — still, pruning during an active render is wasteful and
    the frontend warns against it."""
    cache_dir = settings.cache_dir()
    files_removed = 0
    bytes_freed = 0
    if cache_dir.is_dir():
        for f in cache_dir.iterdir():
            if f.is_file():
                bytes_freed += f.stat().st_size
                f.unlink()
                files_removed += 1
    return CachePruneOut(files_removed=files_removed, bytes_freed=bytes_freed)


@router.get("/settings/models", response_model=list[ModelStatusOut])
def get_model_status(settings: Settings = Depends(get_settings)) -> list[ModelStatusOut]:
    return [
        ModelStatusOut(
            dest=model.dest, size_bytes=model.size,
            present=is_valid(settings.models_dir / model.dest, model),
        )
        for model in MANIFEST
    ]
