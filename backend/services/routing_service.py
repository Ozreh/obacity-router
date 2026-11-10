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
    def profiles(self):
        return PROFILES

    @property
    def modes(self):
        return MODES

    def route(self, lat1: float, lon1: float, lat2: float, lon2: float,
              profile: str = "fastest", mode: str = "foot", rain: float = 0.0,
              ice: float = 0.0, avoid_tolls: bool = False):
        if profile not in PROFILES:
            raise RouteError("Неизвестный профиль")
        if mode not in MODES:
            raise RouteError("Неизвестный режим")
        if not (self._boundary.contains(Point(lon1, lat1)) and self._boundary.contains(Point(lon2, lat2))):
            raise RouteError("Точка за пределами Обамы")

        try:
            origin = ox.distance.nearest_nodes(self._graph, X=lon1, Y=lat1)
            destination = ox.distance.nearest_nodes(self._graph, X=lon2, Y=lat2)
            selected_profile = replace(PROFILES[profile], mode=mode, avoid_tolls=avoid_tolls)
            weather = Weather(rain=max(0.0, min(1.0, rain)), ice=max(0.0, min(1.0, ice)))
            result = self._router.route(origin, destination, selected_profile, weather, astar=False)
        except Exception as error:
            raise RouteError("Маршрут не найден") from error
        if result is None:
            raise RouteError("Между точками нет пути")
        return result
