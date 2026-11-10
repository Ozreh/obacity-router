"""HTTP routes and request/response contracts."""
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from services.routing_service import RouteError

log = logging.getLogger(__name__)
router = APIRouter()


class RouteResponse(BaseModel):
    route: list[list[float]] | None = None
    time_s: int | None = None
    distance_m: int | None = None
    error: str | None = None


class BoundaryResponse(BaseModel):
    name: str
    ring: list[list[float]]


class ProfilesResponse(BaseModel):
    profiles: list[str]
    modes: list[str]


def get_service(request: Request):
    return request.app.state.routing_service


@router.get("/route", response_model=RouteResponse)
def calculate_route(request: Request, lat1: float, lon1: float, lat2: float, lon2: float,
                    profile: str = "fastest", mode: str = "foot", rain: float = 0.0,
                    ice: float = 0.0, avoid_tolls: bool = False):
    try:
        result = get_service(request).route(lat1, lon1, lat2, lon2, profile, mode, rain, ice, avoid_tolls)
        return {
            "route": result["coords"],
            "time_s": round(result["time_s"]),
            "distance_m": round(result["distance_m"]),
        }
    except RouteError as error:
        return {"error": str(error)}
    except Exception as error:
        log.exception("Unexpected route calculation error")
        return {"error": "Маршрут не найден"}


@router.get("/boundary", response_model=BoundaryResponse)
def get_boundary(request: Request):
    return {"name": "Obama", "ring": get_service(request).boundary_ring}


@router.get("/profiles", response_model=ProfilesResponse)
def get_profiles(request: Request):
    service = get_service(request)
    return {"profiles": list(service.profiles), "modes": list(service.modes)}
