
import logging
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from routing import RouteError, RoutingService

log = logging.getLogger(__name__)
router = APIRouter()


class RouteResponse(BaseModel):
    route: Optional[list[list[float]]] = None
    error: Optional[str] = None


class BoundaryResponse(BaseModel):
    name: str
    ring: list[list[float]]


def get_service(request: Request) -> RoutingService:
    return request.app.state.service


@router.get("/route", response_model=RouteResponse, response_model_exclude_none=True)
def calculate_route(request: Request, lat1: float, lon1: float, lat2: float, lon2: float):
    # Обычная def (не async): поиск пути тяжёлый, FastAPI сам запустит его в потоке
    try:
        return {"route": get_service(request).route(lat1, lon1, lat2, lon2)}
    except RouteError as e:
        return {"error": str(e)}
    except Exception:
        log.exception("Неожиданная ошибка построения маршрута")
        return {"error": "Маршрут не найден"}


@router.get("/boundary", response_model=BoundaryResponse)
def get_boundary(request: Request):
    return {"name": "Obama", "ring": get_service(request).boundary.ring}