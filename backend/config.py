"""Application paths and environment-backed settings."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
OSM_FILE = BASE_DIR / "extracted.osm"
BOUNDARY_FILE = BASE_DIR / "obama_boundary.json"
GRAPH_CACHE_FILE = BASE_DIR / "graph_walk.graphml"
FRONTEND_DIR = PROJECT_DIR / "frontend"


def get_cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "*")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
