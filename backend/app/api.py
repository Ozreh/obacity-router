"""HTTP routes and request/response contracts."""
import logging
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from shapely import STRtree
from shapely.geometry import Point, Polygon

import elevation
from services.routing_service import RouteError

log = logging.getLogger(__name__)
router = APIRouter()
ADDRESS_FILE = Path(__file__).resolve().parents[2] / "address-service" / "data" / "obama-addresses.json"
with ADDRESS_FILE.open(encoding="utf-8") as source:
    ADDRESS_DATA = json.load(source)
ADDRESS_POINTS = [Point(item["lon"], item["lat"]) for item in ADDRESS_DATA]
ADDRESS_TREE = STRtree(ADDRESS_POINTS)
OSM_FILE = Path(__file__).resolve().parents[1] / "extracted.osm"
with (Path(__file__).resolve().parents[1] / "obama_boundary.json").open(encoding="utf-8") as source:
    _boundary_ring = json.load(source)["ring"]
_BOUNDARY_POLYGON = Polygon([(point[1], point[0]) for point in _boundary_ring])
_MIN_LAT = min(point[0] for point in _boundary_ring) - 0.01
_MAX_LAT = max(point[0] for point in _boundary_ring) + 0.01
_MIN_LON = min(point[1] for point in _boundary_ring) - 0.01
_MAX_LON = max(point[1] for point in _boundary_ring) + 0.01
POI_ALIASES = {
    "coffee": "coffee", "кофе": "coffee", "кофейня": "coffee", "cafe": "coffee", "кафе": "coffee", "喫茶店": "coffee", "カフェ": "coffee",
    "ramen": "ramen", "рамен": "ramen", "рамэн": "ramen", "ラーメン": "ramen",
    "restaurant": "restaurant", "ресторан": "restaurant", "еда": "restaurant", "бар": "restaurant", "bar": "restaurant", "pub": "restaurant", "паб": "restaurant", "izakaya": "restaurant", "изакая": "restaurant", "居酒屋": "restaurant", "食堂": "restaurant", "レストラン": "restaurant", "food court": "restaurant",
    "shopping": "shopping", "shop": "shopping", "магазин": "shopping", "магазины": "shopping", "магаз": "shopping", "торговый центр": "shopping", "тц": "shopping", "mall": "shopping", "shopping center": "shopping", "shopping centre": "shopping",
    "convenience": "convenience", "convenience store": "convenience", "conbini": "convenience", "コンビニ": "convenience", "конбини": "convenience", "комбини": "convenience", "7-eleven": "convenience", "lawson": "convenience", "familymart": "convenience",
    "supermarket": "supermarket", "супермаркет": "supermarket", "market": "supermarket",
    "healthcare": "healthcare", "медицина": "healthcare", "больница": "healthcare", "больницу": "healthcare", "hospital": "healthcare", "клиника": "healthcare", "clinic": "healthcare", "врач": "healthcare", "doctor": "healthcare", "dentist": "healthcare", "стоматолог": "healthcare", "ветеринар": "healthcare", "veterinary": "healthcare",
    "pharmacy": "pharmacy", "аптека": "pharmacy", "лекарства": "pharmacy", "chemist": "pharmacy",
    "transport": "transport", "транспорт": "transport", "парковка": "transport", "parking": "transport", "бензин": "transport", "fuel": "transport", "автобус": "transport", "bus": "transport", "такси": "transport", "taxi": "transport", "зарядка": "transport", "charging station": "transport",
    "money": "money", "деньги": "money", "банк": "money", "bank": "money", "банкомат": "money", "atm": "money", "почта": "money", "post office": "money",
    "education": "education", "образование": "education", "школа": "education", "school": "education", "детский сад": "education", "kindergarten": "education", "университет": "education", "university": "education", "библиотека": "education", "library": "education",
    "public": "public", "общественное": "public", "полиция": "public", "police": "public", "koban": "public", "мэрия": "public", "town hall": "public", "fire station": "public", "туалет": "public", "туалеты": "public", "toilets": "public", "community centre": "public", "community center": "public",
    "religion": "religion", "храм": "religion", "храмы": "religion", "святилище": "religion", "temple": "religion", "shrine": "religion", "церковь": "religion", "church": "religion",
    "hotel": "stay", "отель": "stay", "гостиница": "stay", "guest house": "stay", "рёкан": "stay", "ryokan": "stay",
    "park": "leisure", "парк": "leisure", "playground": "leisure", "спорт": "leisure", "sports centre": "leisure", "sports center": "leisure", "бассейн": "leisure", "swimming pool": "leisure", "фитнес": "leisure", "fitness": "leisure",
    "culture": "culture", "культура": "culture", "музей": "culture", "museum": "culture", "достопримечательность": "culture", "attraction": "culture", "viewpoint": "culture", "замок": "culture", "castle": "culture", "historic": "culture",
    "vending machine": "services", "автомат": "services", "вендинг": "services", "баня": "services", "онсэн": "services", "onsen": "services", "караоке": "services", "karaoke": "services", "laundry": "services", "прачечная": "services",
    "office": "office", "офис": "office", "компания": "office", "company": "office",
    "building": "building", "здание": "building", "здания": "building", "строение": "building",
    "landuse": "landuse", "территория": "landuse", "территории": "landuse", "район": "landuse",
}

AMENITY_GROUPS = {
    "coffee": {"cafe"}, "restaurant": {"restaurant", "fast_food", "food_court", "bar", "pub", "ice_cream", "izakaya"},
    "healthcare": {"hospital", "clinic", "doctors", "dentist", "veterinary"},
    "pharmacy": {"pharmacy"}, "transport": {"parking", "bicycle_parking", "fuel", "charging_station", "taxi", "bus_station"},
    "money": {"bank", "atm", "post_office"}, "education": {"school", "kindergarten", "university", "library"},
    "public": {"townhall", "police", "fire_station", "community_centre", "toilets"},
    "religion": {"place_of_worship"}, "services": {"vending_machine", "public_bath", "karaoke_box"},
}
SHOP_GROUPS = {
    "convenience": {"convenience"}, "supermarket": {"supermarket"}, "pharmacy": {"chemist"},
    "coffee": {"coffee"}, "shopping": {"bakery", "confectionery", "alcohol", "clothes", "hairdresser", "beauty", "pet", "electronics", "mobile_phone", "books", "hardware", "car", "car_repair", "laundry", "seafood", "department_store", "mall"},
}
TOURISM_GROUPS = {"stay": {"hotel", "guest_house"}, "culture": {"museum", "attraction", "viewpoint", "information"}}
LEISURE_GROUPS = {"leisure": {"park", "playground", "sports_centre", "fitness_centre", "swimming_pool"}}
BUILDING_GROUPS = {
    "shopping": {"commercial", "retail", "supermarket", "kiosk"},
    "office": {"office"}, "healthcare": {"hospital"}, "education": {"school", "university", "kindergarten"},
    "public": {"public", "civic", "government", "train_station"}, "religion": {"temple", "shrine", "church"},
    "stay": {"hotel"}, "transport": {"garage", "garages"},
    "building": {"house", "detached", "apartments", "residential", "terrace", "dormitory", "industrial", "warehouse", "factory", "farm", "barn", "shed", "greenhouse", "roof", "hut", "ruins"},
}


def classify_place(tags: dict[str, str]) -> str | None:
    cuisine = tags.get("cuisine", "").casefold().replace("_", " ")
    amenity = tags.get("amenity", "")
    shop = tags.get("shop", "")
    building = tags.get("building", "")
    if "ramen" in cuisine or "ラーメン" in cuisine:
        return "ramen"
    if amenity == "cafe" or shop == "coffee" or "coffee shop" in cuisine:
        return "coffee"
    for group, values in AMENITY_GROUPS.items():
        if amenity in values:
            return group
    if amenity in {"restaurant", "fast_food", "food_court", "bar", "pub", "ice_cream"}:
        return "restaurant"
    for group, values in SHOP_GROUPS.items():
        if shop in values:
            return group
    for group, values in TOURISM_GROUPS.items():
        if tags.get("tourism", "") in values:
            return group
    if tags.get("historic"):
        return "culture"
    if tags.get("landuse") in {"residential", "commercial", "industrial", "farmland", "forest"} and tags.get("name"):
        return "landuse"
    for group, values in LEISURE_GROUPS.items():
        if tags.get("leisure", "") in values:
            return group
    if tags.get("office"):
        return "office"
    religion = tags.get("religion", "")
    if amenity == "place_of_worship" or religion in {"shinto", "buddhist"}:
        return "religion"
    for group, values in BUILDING_GROUPS.items():
        if building in values:
            return group
    if building == "yes":
        return "building"
    # Keep named buildings below while omitting anonymous residential structures.
    if building and building not in {"yes", "house", "detached", "apartments", "residential", "terrace", "dormitory"}:
        return "building"
    return None


def load_places() -> list[dict]:
    """Read named POIs and useful buildings from the bundled OSM extract."""
    if not OSM_FILE.exists():
        return []
    places = []
    nearby_nodes = {}
    for _, element in ET.iterparse(OSM_FILE, events=("end",)):
        if element.tag == "node":
            try:
                lat, lon = float(element.attrib["lat"]), float(element.attrib["lon"])
            except (KeyError, ValueError):
                element.clear()
                continue
            if _MIN_LAT <= lat <= _MAX_LAT and _MIN_LON <= lon <= _MAX_LON:
                nearby_nodes[element.attrib["id"]] = (lat, lon)
            else:
                element.clear()
                continue
            if not _BOUNDARY_POLYGON.contains(Point(lon, lat)):
                element.clear()
                continue
            tags = {tag.attrib.get("k"): tag.attrib.get("v", "") for tag in element.findall("tag")}
            refs = []
        elif element.tag == "way":
            tags = {tag.attrib.get("k"): tag.attrib.get("v", "") for tag in element.findall("tag")}
            refs = [child.attrib.get("ref") for child in element.findall("nd")]
            coords = [nearby_nodes[ref] for ref in refs if ref in nearby_nodes]
            if not coords:
                element.clear()
                continue
            lat = sum(point[0] for point in coords) / len(coords)
            lon = sum(point[1] for point in coords) / len(coords)
            if not _BOUNDARY_POLYGON.contains(Point(lon, lat)):
                element.clear()
                continue
        else:
            continue
        kind = classify_place(tags)
        if not kind:
            element.clear()
            continue
        name = tags.get("name") or tags.get("name:en") or tags.get("name:ru")
        if not name and kind == "building":
            element.clear()
            continue
        if not name:
            name = tags.get("brand") or {
                "coffee": "Кафе", "ramen": "Рамен", "restaurant": "Ресторан",
                "shopping": "Магазин", "convenience": "Конбини", "supermarket": "Супермаркет",
                "healthcare": "Медицинский пункт", "pharmacy": "Аптека", "transport": "Транспорт",
                "money": "Банк / банкомат / почта", "education": "Учебное заведение", "public": "Городская служба",
                "religion": "Храм / святилище", "stay": "Отель / гостевой дом", "leisure": "Парк / спорт",
                "culture": "Достопримечательность", "services": "Услуги", "office": "Офис",
            }.get(kind, "Место")
        display_names = list(dict.fromkeys(value.strip() for value in (
            tags.get("name", ""), tags.get("name:en", ""), tags.get("name:ja-Latn", ""), name,
        ) if value and value.strip()))
        label = " · ".join(display_names)
        search_fields = [name, tags.get("name:en", ""), tags.get("name:ru", ""), tags.get("name:ja-Latn", ""), tags.get("name:ja", ""),
                         tags.get("brand", ""), tags.get("brand:en", ""), tags.get("cuisine", ""),
                         tags.get("amenity", ""), tags.get("shop", ""), tags.get("tourism", ""),
                         tags.get("leisure", ""), tags.get("historic", ""), tags.get("building", ""),
                         tags.get("religion", ""), tags.get("office", ""), tags.get("landuse", ""),
                         tags.get("opening_hours", ""), tags.get("phone", ""), tags.get("website", "")]
        places.append({
            "id": f"{element.tag}/{element.attrib.get('id')}", "label": label, "lat": lat, "lon": lon,
            "kind": kind, "brand": tags.get("brand", ""),
            "opening_hours": tags.get("opening_hours", ""), "phone": tags.get("phone", ""),
            "website": tags.get("website", ""), "search": " ".join(search_fields).casefold(),
        })
        element.clear()
    return places


PLACES = load_places()


class RouteResponse(BaseModel):
    route: list[list[float]] | None = None
    time_s: int | None = None
    distance_m: int | None = None
    error: str | None = None
    slope: dict | None = None


class BoundaryResponse(BaseModel):
    name: str
    ring: list[list[float]]


class ProfilesResponse(BaseModel):
    profiles: list[str]
    modes: list[str]


def get_service(request: Request):
    return request.app.state.routing_service


def public_place(place: dict) -> dict:
    return {key: place[key] for key in ("id", "label", "lat", "lon", "kind", "brand", "opening_hours", "phone", "website")}


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
            "slope": elevation.slope_segments(result["coords"]),
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
    limit: int = Query(default=8, ge=1, le=500),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    category: str | None = Query(default=None, max_length=30),
):
    query = " ".join(q.casefold().split())
    normalized_query = POI_ALIASES.get(query, query)
    category_key = POI_ALIASES.get((category or "").casefold(), (category or "").casefold())
    matches = []
    known_categories = {place["kind"] for place in PLACES}
    if not category_key and normalized_query in known_categories:
        category_key = normalized_query
    if category_key in known_categories:
        selected_category = category_key
        for place in PLACES:
            if place["kind"] != selected_category and not (selected_category == "restaurant" and place["kind"] == "ramen"):
                continue
            distance = (place["lat"] - lat) ** 2 + (place["lon"] - lon) ** 2 if lat is not None and lon is not None else 0
            matches.append((0, distance, public_place(place)))
        matches.sort(key=lambda result: (result[1], result[2]["label"].casefold()))
        return [result[2] for result in matches[:max(limit, 500)]]
    for place in PLACES:
        if normalized_query not in place["search"]:
            continue
        distance = (place["lat"] - lat) ** 2 + (place["lon"] - lon) ** 2 if lat is not None and lon is not None else 0
        matches.append((0, distance, public_place(place)))
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
    matches.sort(key=lambda result: (result[0], result[1], result[2]["label"].casefold()))
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
