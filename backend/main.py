import json
from dataclasses import replace
from pathlib import Path

import networkx as nx
import osmnx as ox
import shapely
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from shapely.geometry import Point, Polygon

from auth import current_user, lifespan as auth_lifespan, router as auth_router
from router_engine import MODES, PROFILES, Router, Weather

app = FastAPI(lifespan=auth_lifespan)
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
OSM_FILE = BASE_DIR / "extracted.osm"
BOUNDARY_FILE = BASE_DIR / "obama_boundary.json"
FRONTEND_DIR = BASE_DIR.parent / "frontend"
CACHE_FILE = BASE_DIR / "graph_walk.graphml"

BAD_HIGHWAYS = {"motorway", "motorway_link", "construction", "proposed", "raceway", "bus_guideway"}

with open(BOUNDARY_FILE, encoding="utf-8") as f:
    RING = json.load(f)["ring"]
BOUNDARY = Polygon([(lon, lat) for lat, lon in RING])
shapely.prepare(BOUNDARY)


def _is_walkable(data: dict) -> bool:
    hw = data.get("highway")
    if hw is None:
        return False
    hw = hw if isinstance(hw, list) else [hw]
    if all(h in BAD_HIGHWAYS for h in hw):
        return False
    if data.get("foot") == "no" or data.get("access") in ("no", "private"):
        return False
    return True


def build_graph():
    g = ox.graph_from_xml(OSM_FILE, bidirectional=True, simplify=False, retain_all=True)

    bad = [(u, v, k) for u, v, k, d in g.edges(keys=True, data=True) if not _is_walkable(d)]
    g.remove_edges_from(bad)
    g.remove_nodes_from(list(nx.isolates(g)))

    ids = list(g.nodes)
    xs = [g.nodes[n]["x"] for n in ids]
    ys = [g.nodes[n]["y"] for n in ids]
    inside = shapely.contains_xy(BOUNDARY, xs, ys)
    g.remove_nodes_from([n for n, ok in zip(ids, inside) if not ok])
    g.remove_nodes_from(list(nx.isolates(g)))

    biggest = max(nx.weakly_connected_components(g), key=len)
    return g.subgraph(biggest).copy()


def load_graph():
    newest_source = max(OSM_FILE.stat().st_mtime, BOUNDARY_FILE.stat().st_mtime)
    if CACHE_FILE.exists() and CACHE_FILE.stat().st_mtime > newest_source:
        return ox.load_graphml(CACHE_FILE)
    g = build_graph()
    ox.save_graphml(g, CACHE_FILE)
    return g


G = load_graph()
ROUTER = Router(G)
print(f"Граф загружен: {len(G.nodes)} узлов, {len(G.edges)} рёбер")


@app.get("/boundary")
def get_boundary(_user: dict = Depends(current_user)):
    return {"name": "Obama", "ring": RING}


@app.get("/profiles")
def get_profiles(_user: dict = Depends(current_user)):
    return {"profiles": list(PROFILES), "modes": list(MODES)}


@app.get("/route")
def calculate_route(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    profile: str = "fastest",
    mode: str = "foot",
    rain: float = 0.0,
    ice: float = 0.0,
    avoid_tolls: bool = False,
    _user: dict = Depends(current_user),
):
    if profile not in PROFILES:
        return {"error": "Неизвестный профиль"}
    if mode not in MODES:
        return {"error": "Неизвестный режим"}
    if not (BOUNDARY.contains(Point(lon1, lat1)) and BOUNDARY.contains(Point(lon2, lat2))):
        return {"error": "Точка за пределами Обамы"}
    try:
        orig_node = ox.distance.nearest_nodes(G, X=lon1, Y=lat1)
        dest_node = ox.distance.nearest_nodes(G, X=lon2, Y=lat2)
        prof = replace(PROFILES[profile], mode=mode, avoid_tolls=avoid_tolls)
        weather = Weather(rain=max(0.0, min(1.0, rain)), ice=max(0.0, min(1.0, ice)))
        result = ROUTER.route(orig_node, dest_node, prof, weather, astar=False)
    except Exception as e:
        print("route error:", repr(e))
        return {"error": "Маршрут не найден"}

    if result is None:
        return {"error": "Между точками нет пути"}
    return {
        "route": result["coords"],
        "time_s": round(result["time_s"]),
        "distance_m": round(result["distance_m"]),
    }


if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
