"""User-adjustable runtime settings (worker count, loudness target), stored as
key/value rows in the Setting table. Distinct from config.py's Settings, which is
env-driven and fixed for a process's lifetime — these are meant to change from the
Settings page (M3-7) without restarting the backend. See PLAN.md.
"""
from sqlmodel import Session, select

from .audio import loudness
from .models import Setting
from .publish.split import DEFAULT_PART_LIMIT_S
from .tts.pool import DEFAULT_WORKERS

DEFAULTS: dict[str, str] = {
    "tts_workers": str(DEFAULT_WORKERS),
    "loudness_target_i": str(loudness.DEFAULT_TARGET_I),
    "loudness_target_tp": str(loudness.DEFAULT_TARGET_TP),
    "loudness_target_lra": str(loudness.DEFAULT_TARGET_LRA),
    "mp4_part_limit_s": str(DEFAULT_PART_LIMIT_S),
}


class UnknownSettingError(Exception):
    pass


def get_all(session: Session) -> dict[str, str]:
    rows = session.exec(select(Setting)).all()
    values = dict(DEFAULTS)
    values.update({row.key: row.value for row in rows if row.key in DEFAULTS})
    return values


def get_typed(session: Session) -> dict[str, int | float]:
    values = get_all(session)
    return {
        "tts_workers": int(values["tts_workers"]),
        "loudness_target_i": float(values["loudness_target_i"]),
        "loudness_target_tp": float(values["loudness_target_tp"]),
        "loudness_target_lra": float(values["loudness_target_lra"]),
        "mp4_part_limit_s": float(values["mp4_part_limit_s"]),
    }


def set_many(session: Session, updates: dict[str, str]) -> None:
    for key in updates:
        if key not in DEFAULTS:
            raise UnknownSettingError(f"unknown setting key: {key!r} (known: {sorted(DEFAULTS)})")
    for key, value in updates.items():
        row = session.get(Setting, key)
        if row is None:
            row = Setting(key=key, value=value)
        else:
            row.value = value
        session.add(row)
    session.commit()
