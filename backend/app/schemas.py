"""Pydantic request/response models for the API. Grows with each milestone's endpoints."""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
