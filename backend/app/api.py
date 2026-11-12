"""HTTP routes and request/response contracts."""
import logging
import json
from pathlib import Path

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from shapely import STRtree
from shapely.geometry import Point

from services.routing_service import RouteError

log = logging.getLogger(__name__)
router = APIRouter()
ADDRESS_FILE = Path(__file__).resolve().parents[2] / "address-service" / "data" / "obama-addresses.json"
with ADDRESS_FILE.open(encoding="utf-8") as source:
    ADDRESS_DATA = json.load(source)
ADDRESS_POINTS = [Point(item["lon"], item["lat"]) for item in ADDRESS_DATA]
ADDRESS_TREE = STRtree(ADDRESS_POINTS)


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
                    ice: float = 0.0, avoid_tolls: bool = False,
                    waypoints: str | None = Query(default=None, max_length=2000)):
    try:
        parsed_waypoints = []
        if waypoints:
            parsed_waypoints = [(float(pair.split(",")[0]), float(pair.split(",")[1]))
                                for pair in waypoints.split(";")]
            if len(parsed_waypoints) > 8 or any(not (-90 <= lat <= 90 and -180 <= lon <= 180)
                                                   for lat, lon in parsed_waypoints):
                return {"error": "Некорректные промежуточные остановки"}
        result = get_service(request).route(lat1, lon1, lat2, lon2, profile, mode, rain, ice,
                                            avoid_tolls, parsed_waypoints)
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


@router.get("/search")
def search_addresses(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=8, ge=1, le=20),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
):
    query = " ".join(q.casefold().split())
    matches = []
    for item in ADDRESS_DATA:
        street = item.get("street", "")
        house = item.get("house", "")
        label = " ".join(part.strip() for part in (street, house) if part and part.strip()) or "小浜市"
        tokens = f"{label} 小浜市 Obama".casefold().split()
        matching_tokens = [token for token in tokens if token.startswith(query)]
        if matching_tokens or query in " ".join(tokens):
            rank = 0 if label.casefold().startswith(query) else 1 if matching_tokens else 2
            distance = (item["lat"] - lat) ** 2 + (item["lon"] - lon) ** 2 if lat is not None and lon is not None else 0
            matches.append((rank, distance, {
                "id": f"{item['lat']}:{item['lon']}", "label": label, "city": "Obama",
                "lat": item["lat"], "lon": item["lon"],
            }))
    matches.sort(key=lambda result: (result[0], result[1], result[2]["label"]))
    return [result[2] for result in matches[:limit]]


@router.get("/reverse")
def reverse_geocode(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    point = Point(lon, lat)
    nearest = int(ADDRESS_TREE.nearest(point))
    item = ADDRESS_DATA[nearest]
    street = item.get("street", "").strip()
    house = item.get("house", "").strip()
    label = " ".join(part for part in (street, house) if part) or "小浜市"
    distance_m = point.distance(ADDRESS_POINTS[nearest]) * 111_000
    return {"label": label, "street": street, "house_number": house or None, "distance_m": round(distance_m)}
