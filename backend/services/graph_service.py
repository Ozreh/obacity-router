"""Loads and filters the local OSM graph used for routing."""
import json

import networkx as nx
import osmnx as ox
import shapely
from shapely.geometry import Polygon

from config import BOUNDARY_FILE, GRAPH_CACHE_FILE, OSM_FILE

BAD_HIGHWAYS = {"motorway", "motorway_link", "construction", "proposed", "raceway", "bus_guideway"}


def load_boundary() -> tuple[list[list[float]], Polygon]:
    with BOUNDARY_FILE.open(encoding="utf-8") as source:
        ring = json.load(source)["ring"]
    boundary = Polygon([(lon, lat) for lat, lon in ring])
    shapely.prepare(boundary)
    return ring, boundary


def is_walkable(data: dict) -> bool:
    highways = data.get("highway")
    if highways is None:
        return False
    highways = highways if isinstance(highways, list) else [highways]
    return not (
        all(highway in BAD_HIGHWAYS for highway in highways)
        or data.get("foot") == "no"
        or data.get("access") in ("no", "private")
    )


def build_graph():
    graph = ox.graph_from_xml(OSM_FILE, bidirectional=True, simplify=False, retain_all=True)
    graph.remove_edges_from(
        [(u, v, key) for u, v, key, data in graph.edges(keys=True, data=True) if not is_walkable(data)]
    )
    graph.remove_nodes_from(list(nx.isolates(graph)))

    nodes = list(graph.nodes)
    inside = shapely.contains_xy(
        load_boundary()[1],
        [graph.nodes[node]["x"] for node in nodes],
        [graph.nodes[node]["y"] for node in nodes],
    )
    graph.remove_nodes_from([node for node, keep in zip(nodes, inside) if not keep])
    graph.remove_nodes_from(list(nx.isolates(graph)))
    component = max(nx.weakly_connected_components(graph), key=len)
    return graph.subgraph(component).copy()


def load_graph():
    newest_source = max(OSM_FILE.stat().st_mtime, BOUNDARY_FILE.stat().st_mtime)
    if GRAPH_CACHE_FILE.exists() and GRAPH_CACHE_FILE.stat().st_mtime > newest_source:
        return ox.load_graphml(GRAPH_CACHE_FILE)
    graph = build_graph()
    ox.save_graphml(graph, GRAPH_CACHE_FILE)
    return graph
