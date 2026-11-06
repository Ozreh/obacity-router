import json
from pathlib import Path

import networkx as nx
import osmnx as ox
import shapely
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shapely.geometry import Point, Polygon

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Пути считаем от папки, где лежит main.py, а не от места запуска uvicorn
BASE_DIR = Path(__file__).resolve().parent
OSM_FILE = BASE_DIR / "extracted.osm"
BOUNDARY_FILE = BASE_DIR / "obama_boundary.json"
CACHE_FILE = BASE_DIR / "graph_walk.graphml"  # готовый граф, чтобы не парсить 80 МБ при каждом старте

# Дороги, по которым пешком не ходят
BAD_HIGHWAYS = {"motorway", "motorway_link", "construction", "proposed", "raceway", "bus_guideway"}

# --- Граница Обамы -----------------------------------------------------------
# В файле кольцо хранится как [[lat, lon], ...], а shapely ждёт (x=lon, y=lat)
with open(BOUNDARY_FILE, encoding="utf-8") as f:
    RING = json.load(f)["ring"]
BOUNDARY = Polygon([(lon, lat) for lat, lon in RING])
shapely.prepare(BOUNDARY)  # ускоряет проверки «точка внутри»


def _is_walkable(data: dict) -> bool:
    """Оставляем только рёбра-дороги, подходящие для пешехода."""
    hw = data.get("highway")
    if hw is None:  # здания, ж/д, границы и прочее — не дороги
        return False
    hw = hw if isinstance(hw, list) else [hw]
    if all(h in BAD_HIGHWAYS for h in hw):
        return False
    if data.get("foot") == "no" or data.get("access") in ("no", "private"):
        return False
    return True


def build_graph():
    # bidirectional=True: пешеходу не важны односторонние улицы
    # simplify=False: сначала фильтруем, и так сохраняется точная форма дорог
    g = ox.graph_from_xml(OSM_FILE, bidirectional=True, simplify=False, retain_all=True)

    # Выкидываем всё, что не дорога (в .osm 30 000 зданий)
    bad = [(u, v, k) for u, v, k, d in g.edges(keys=True, data=True) if not _is_walkable(d)]
    g.remove_edges_from(bad)
    g.remove_nodes_from(list(nx.isolates(g)))

    # Обрезаем граф по границе Обамы: узлы снаружи удаляются вместе со своими рёбрами
    ids = list(g.nodes)
    xs = [g.nodes[n]["x"] for n in ids]
    ys = [g.nodes[n]["y"] for n in ids]
    inside = shapely.contains_xy(BOUNDARY, xs, ys)
    g.remove_nodes_from([n for n, ok in zip(ids, inside) if not ok])
    g.remove_nodes_from(list(nx.isolates(g)))

    # Оставляем самую большую связную часть, иначе точки попадают на «острова»
    biggest = max(nx.weakly_connected_components(g), key=len)
    return g.subgraph(biggest).copy()


def load_graph():
    # Кэш актуален, только если он свежее и .osm, и границы (иначе пересобираем)
    newest_source = max(OSM_FILE.stat().st_mtime, BOUNDARY_FILE.stat().st_mtime)
    if CACHE_FILE.exists() and CACHE_FILE.stat().st_mtime > newest_source:
        return ox.load_graphml(CACHE_FILE)
    g = build_graph()
    ox.save_graphml(g, CACHE_FILE)
    return g


G = load_graph()
print(f"Граф загружен: {len(G.nodes)} узлов, {len(G.edges)} рёбер")


@app.get("/boundary")
def get_boundary():
    # Отдаём границу фронтенду в формате Leaflet: [[lat, lon], ...]
    return {"name": "Obama", "ring": RING}


@app.get("/route")
def calculate_route(lat1: float, lon1: float, lat2: float, lon2: float):
    # Обе точки должны лежать внутри границы Обамы
    if not (BOUNDARY.contains(Point(lon1, lat1)) and BOUNDARY.contains(Point(lon2, lat2))):
        return {"error": "Точка за пределами Обамы"}
    try:
        # Числа, а не списки — тогда возвращается один id узла, а не массив
        orig_node = ox.distance.nearest_nodes(G, X=lon1, Y=lat1)
        dest_node = ox.distance.nearest_nodes(G, X=lon2, Y=lat2)
        # weight="length" — кратчайший по метрам, а не по числу перекрёстков
        route_nodes = nx.shortest_path(G, source=orig_node, target=dest_node, weight="length")
    except nx.NetworkXNoPath:
        return {"error": "Между точками нет пешего пути"}
    except Exception as e:
        print("route error:", repr(e))  # видно причину в консоли uvicorn
        return {"error": "Маршрут не найден"}

    route_coords = [[G.nodes[n]["y"], G.nodes[n]["x"]] for n in route_nodes]
    return {"route": route_coords}