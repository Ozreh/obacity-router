"""Backward-compatible Uvicorn entry point: uvicorn main:app."""
from app.application import app

__all__ = ["app"]
