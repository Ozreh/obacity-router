import logging
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests
from PIL import Image

from config import BASE_DIR

log = logging.getLogger(__name__)

TILE_DIR = BASE_DIR / "cache" / "dem"
TILE_URL = "https://cyberjapandata.gsi.go.jp/xyz/{src}/{z}/{x}/{y}.png"
SOURCES = (("dem5a_png", 15), ("dem_png", 14))
MAX_NET_FAILURES = 5
WORKERS = 8

_tiles: dict = {}
_session = requests.Session()
_net_failures = 0
_MISSING = object()


def tile_pos(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    fx = (lon + 180.0) / 360.0 * n
    fy = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return fx, fy


def _decode(path) -> np.ndarray:
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.int64)
    raw = rgb[..., 0] * 65536 + rgb[..., 1] * 256 + rgb[..., 2]
    height = np.where(raw < 2 ** 23, raw, raw - 2 ** 24) * 0.01
    height = height.astype(np.float32)
    height[raw == 2 ** 23] = np.nan
    return height


def _tile(src: str, z: int, x: int, y: int, download: bool):
    global _net_failures
    key = (src, z, x, y)
    cached = _tiles.get(key)
    if cached is not None:
        return None if cached is _MISSING else cached
    path = TILE_DIR / f"{src}_{z}_{x}_{y}.png"
    marker = path.with_suffix(".none")
    if path.exists():
        _tiles[key] = _decode(path)
        return _tiles[key]
    if marker.exists():
        _tiles[key] = _MISSING
        return None
    if not download or _net_failures >= MAX_NET_FAILURES:
        return None
    try:
        response = _session.get(TILE_URL.format(src=src, z=z, x=x, y=y), timeout=(5, 15))
    except requests.RequestException as error:
        _net_failures += 1
        log.warning("Тайл высот %s недоступен: %s", key, error)
        return None
    _net_failures = 0
    TILE_DIR.mkdir(parents=True, exist_ok=True)
    if response.status_code == 200:
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(response.content)
        tmp.replace(path)
        _tiles[key] = _decode(path)
        return _tiles[key]
    if response.status_code in (403, 404):
        marker.write_bytes(b"")
        _tiles[key] = _MISSING
    else:
        log.warning("Тайл высот %s: HTTP %s", key, response.status_code)
    return None


def _sample(src: str, z: int, lat: float, lon: float, download: bool):
    fx, fy = tile_pos(lat, lon, z)
    x, y = int(fx), int(fy)
    tile = _tile(src, z, x, y, download)
    if tile is None:
        return None
    px = min(max((fx - x) * 256 - 0.5, 0.0), 255.0)
    py = min(max((fy - y) * 256 - 0.5, 0.0), 255.0)
    x0, y0 = int(px), int(py)
    x1, y1 = min(x0 + 1, 255), min(y0 + 1, 255)
    tx, ty = px - x0, py - y0
    corners = (tile[y0, x0], tile[y0, x1], tile[y1, x0], tile[y1, x1])
    if any(math.isnan(float(c)) for c in corners):
        return None
    top = corners[0] * (1 - tx) + corners[1] * tx
    bottom = corners[2] * (1 - tx) + corners[3] * tx
    return float(top * (1 - ty) + bottom * ty)


def elevation(lat: float, lon: float, download: bool = True):
    for src, z in SOURCES:
        value = _sample(src, z, lat, lon, download)
        if value is not None:
            return value
    return None


def prefetch(points: list[tuple[float, float]]) -> None:
    remaining = list(points)
    for src, z in SOURCES:
        if not remaining:
            return
        tiles = {tuple(int(v) for v in tile_pos(lat, lon, z)) for lat, lon in remaining}
        log.warning("Загрузка тайлов высот %s: %d", src, len(tiles))
        with ThreadPoolExecutor(WORKERS) as pool:
            list(pool.map(lambda t: _tile(src, z, t[0], t[1], True), tiles))
        remaining = [p for p in remaining if _sample(src, z, p[0], p[1], False) is None]


def attach_to_graph(graph) -> int:
    points = [(float(d["y"]), float(d["x"])) for _, d in graph.nodes(data=True)]
    prefetch(points)
    found = 0
    for node, data in graph.nodes(data=True):
        value = elevation(float(data["y"]), float(data["x"]), download=False)
        if value is not None:
            data["elevation"] = value
            found += 1
    return found
