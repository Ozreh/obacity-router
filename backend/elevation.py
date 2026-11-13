import json
import math
import threading

import requests

from config import BASE_DIR

CACHE_FILE = BASE_DIR / "cache" / "elevation_cache.json"
API_URL = "https://api.open-meteo.com/v1/elevation"
BATCH = 100
CHUNK_M = 35.0
CLASSES = [
    ("steep_up", "Крутой подъём", "#dc2626"),
    ("up", "Подъём", "#f97316"),
    ("flat", "Ровно", "#2563eb"),
    ("down", "Спуск", "#22c55e"),
    ("steep_down", "Крутой спуск", "#0d9488"),
]

_lock = threading.Lock()
_cache: dict[str, float] | None = None


def _key(lat: float, lon: float) -> str:
    return f"{lat:.5f},{lon:.5f}"


def _load() -> dict[str, float]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _save() -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(_cache), encoding="utf-8")


def fetch_elevations(points: list[list[float]]) -> list[float] | None:
    with _lock:
        cache = _load()
        missing = []
        seen = set()
        for lat, lon in points:
            k = _key(lat, lon)
            if k not in cache and k not in seen:
                seen.add(k)
                missing.append((lat, lon))
        try:
            for i in range(0, len(missing), BATCH):
                part = missing[i:i + BATCH]
                response = requests.get(API_URL, params={
                    "latitude": ",".join(f"{lat:.5f}" for lat, _ in part),
                    "longitude": ",".join(f"{lon:.5f}" for _, lon in part),
                }, timeout=10)
                response.raise_for_status()
                values = response.json()["elevation"]
                for (lat, lon), value in zip(part, values):
                    cache[_key(lat, lon)] = float(value)
        except Exception:
            return None
        if missing:
            _save()
        return [cache[_key(lat, lon)] for lat, lon in points]


def _dist(a, b) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 12742000.0 * math.asin(min(1.0, math.sqrt(h)))


def classify(grade: float) -> str:
    if grade >= 0.08:
        return "steep_up"
    if grade >= 0.03:
        return "up"
    if grade > -0.03:
        return "flat"
    if grade > -0.08:
        return "down"
    return "steep_down"


def slope_segments(coords: list[list[float]]) -> dict | None:
    if len(coords) < 2:
        return None
    elevations = fetch_elevations(coords)
    if elevations is None:
        return None

    cum = [0.0]
    for i in range(1, len(coords)):
        cum.append(cum[-1] + _dist(coords[i - 1], coords[i]))

    smooth = []
    for i in range(len(coords)):
        lo, hi = i, i
        while lo > 0 and cum[i] - cum[lo - 1] <= 45:
            lo -= 1
        while hi < len(coords) - 1 and cum[hi + 1] - cum[i] <= 45:
            hi += 1
        smooth.append(sum(elevations[lo:hi + 1]) / (hi - lo + 1))

    segments = []
    gain = loss = 0.0
    start = 0
    for i in range(1, len(coords)):
        length = cum[i] - cum[start]
        if length >= CHUNK_M or i == len(coords) - 1:
            dz = smooth[i] - smooth[start]
            grade = dz / length if length > 1.0 else 0.0
            segments.append({"coords": coords[start:i + 1], "cls": classify(grade), "grade": round(grade * 100, 1)})
            if dz > 0:
                gain += dz
            else:
                loss -= dz
            start = i

    merged = []
    for seg in segments:
        if merged and merged[-1]["cls"] == seg["cls"]:
            merged[-1]["coords"].extend(seg["coords"][1:])
        else:
            merged.append(seg)
    return {
        "segments": merged,
        "gain_m": round(gain),
        "loss_m": round(loss),
        "min_m": round(min(smooth)),
        "max_m": round(max(smooth)),
    }
