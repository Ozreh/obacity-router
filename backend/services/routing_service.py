"""Coordinates validation, graph lookup, and route calculation."""
from dataclasses import replace

import osmnx as ox
from shapely.geometry import Point, Polygon

from router_engine import MODES, PROFILES, Router, Weather


class RouteError(ValueError):
    """A route could not be calculated for a user-correctable reason."""


class RoutingService:
    def __init__(self, graph, boundary_ring: list[list[float]], boundary: Polygon):
        self._graph = graph
        self._boundary_ring = boundary_ring
        self._boundary = boundary
        self._router = Router(graph)

    @property
    def boundary_ring(self):
        return self._boundary_ring

    @property
    def boundary(self):
        return self._boundary

    @property
    def profiles(self):
        return PROFILES

    @property
    def modes(self):
        return MODES

    def route(self, lat1: float, lon1: float, lat2: float, lon2: float,
              profile: str = "fastest", mode: str = "foot", rain: float = 0.0,
              ice: float = 0.0, avoid_tolls: bool = False,
              waypoints: list[tuple[float, float]] | None = None):
        if profile not in PROFILES:
            raise RouteError("Неизвестный профиль")
        if mode not in MODES:
            raise RouteError("Неизвестный режим")
        points = [(lat1, lon1), *(waypoints or []), (lat2, lon2)]
        if any(not self._boundary.contains(Point(lon, lat)) for lat, lon in points):
            raise RouteError("Точка за пределами Обамы")

        try:
            nodes = [ox.distance.nearest_nodes(self._graph, X=lon, Y=lat) for lat, lon in points]
            selected_profile = replace(PROFILES[profile], mode=mode, avoid_tolls=avoid_tolls)
            weather = Weather(rain=max(0.0, min(1.0, rain)), ice=max(0.0, min(1.0, ice)))
            segments = [self._router.route(start, end, selected_profile, weather, astar=False)
                        for start, end in zip(nodes, nodes[1:])]
        except Exception as error:
            raise RouteError("Маршрут не найден") from error
        if any(segment is None for segment in segments):
            raise RouteError("Между точками нет пути")
        coords = []
        distance_m = 0
        time_s = 0
        for segment in segments:
            coords.extend(segment["coords"] if not coords else segment["coords"][1:])
            distance_m += segment["distance_m"]
            time_s += segment["time_s"]
        return {"coords": coords, "distance_m": distance_m, "time_s": time_s}
