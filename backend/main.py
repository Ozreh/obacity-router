from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import osmnx as ox
import networkx as nx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

G = ox.graph_from_xml("extracted.osm", simplify=True)

@app.get("/route")
def calculate_route(lat1: float, lon1: float, lat2: float, lon2: float):
    try:
        orig_node = ox.distance.nearest_nodes(G, X=[lon1], Y=[lat1])
        dest_node = ox.distance.nearest_nodes(G, X=[lon2], Y=[lat2])
        
        route_nodes = nx.shortest_path(G, source=orig_node, target=dest_node)
    except Exception as e:
        return {"error": "Маршрут не найден"}
    
    route_coords = [[G.nodes[node]['y'], G.nodes[node]['x']] for node in route_nodes]
    
    return {"route": route_coords}