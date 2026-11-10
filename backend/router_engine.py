from __future__ import annotations

import heapq
import itertools
import math
import re
from dataclasses import dataclass, field, replace

TOLL_PENALTY = 1e6
HEURISTIC_LB = 0.6
U_TURN_S = 60.0
LEFT_TURN_S = 18.0
RIGHT_TURN_S = 2.0
TURN_MIN_ANGLE = 30.0
U_TURN_ANGLE = 155.0

DEFAULT_SPEED_KMH = {
    "motorway": 110, "motorway_link": 60, "trunk": 90, "trunk_link": 50,
    "primary": 70, "primary_link": 40, "secondary": 60, "secondary_link": 40,
    "tertiary": 50, "tertiary_link": 40, "unclassified": 40, "residential": 40,
    "living_street": 20, "service": 20, "track": 25, "path": 15,
}

LANE_FACTOR = {
    "motorway": 0.85, "motorway_link": 0.9, "trunk": 0.9, "trunk_link": 0.95,
    "primary": 0.95, "secondary": 1.0, "tertiary": 1.0, "unclassified": 1.05,
    "residential": 1.1, "living_street": 1.25, "service": 1.3, "track": 1.3,
}

SURFACE_Q = {
    "asphalt": 1.0, "paved": 1.0, "concrete": 1.0, "concrete:plates": 1.1,
    "paving_stones": 1.3, "sett": 1.4, "cobblestone": 1.5, "compacted": 1.4,
    "fine_gravel": 1.5, "gravel": 1.7, "unpaved": 1.8, "dirt": 1.9, "ground": 1.9,
    "earth": 1.9, "grass": 2.2, "sand": 2.5, "mud": 2.8,
}
SMOOTHNESS_Q = {"bad": 2.0, "very_bad": 3.0, "horrible": 3.5, "very_horrible": 4.0, "impassable": 5.0}
TRACKTYPE_Q = {"grade1": 1.2, "grade2": 1.5, "grade3": 1.8, "grade4": 2.2, "grade5": 2.6}


@dataclass(frozen=True)
class Mode:
    name: str
    cap_kmh: float
    fixed_speed: bool
    forbidden: frozenset
    access_key: str
    hill_k: float
    turn_scale: float
    q_pow: float
    traffic_aware: bool
    use_lane_factor: bool
    delays: dict = field(default_factory=dict, hash=False, compare=False)


MOTOR_BAN = frozenset({"footway", "path", "steps", "pedestrian", "cycleway", "bridleway", "corridor", "construction", "proposed", "raceway", "bus_guideway"})
SLOW_BAN = frozenset({"motorway", "motorway_link", "construction", "proposed", "raceway", "bus_guideway"})

MODES = {
    "car": Mode("car", 130, False, MOTOR_BAN, "motor_vehicle", 0.3, 1.0, 1.0, True, True,
                {"traffic_signals": 30, "crossing": 6, "stop": 10, "give_way": 4, "mini_roundabout": 4, "junction": 3}),
    "truck": Mode("truck", 80, False, MOTOR_BAN | {"track"}, "motor_vehicle", 2.0, 1.5, 1.2, True, True,
                  {"traffic_signals": 35, "crossing": 8, "stop": 14, "give_way": 6, "mini_roundabout": 8, "junction": 4}),
    "bike": Mode("bike", 20, False, SLOW_BAN | {"steps", "trunk"}, "bicycle", 1.5, 0.3, 0.8, False, False,
                 {"traffic_signals": 20, "crossing": 4, "stop": 5, "give_way": 2, "mini_roundabout": 2, "junction": 1}),
    "foot": Mode("foot", 5.04, True, SLOW_BAN, "foot", 1.0, 0.05, 0.5, False, False,
                 {"traffic_signals": 20, "crossing": 5, "stop": 0, "give_way": 0, "mini_roundabout": 0, "junction": 0}),
}


@dataclass(frozen=True)
class Profile:
    name: str
    mode: str = "car"
    w_time: float = 1.0
    w_dist: float = 0.0
    w_climb: float = 0.0
    traffic_exp: float = 1.0
    hill_mult: float = 1.0
    delay_scale: float = 1.0
    turn_scale: float = 1.0
    q_mult: float = 1.0
    avoid_tolls: bool = False


PROFILES = {
    "fastest": Profile("fastest"),
    "shortest": Profile("shortest", w_time=0.02, w_dist=1.0, traffic_exp=0.0, delay_scale=0.0, turn_scale=0.0),
    "eco": Profile("eco", w_time=1.0, w_dist=0.1, w_climb=8.0, hill_mult=3.0, delay_scale=1.5, turn_scale=1.5),
    "no_traffic": Profile("no_traffic", traffic_exp=2.5),
    "comfort": Profile("comfort", w_dist=0.1, w_climb=3.0, hill_mult=2.0, delay_scale=1.5, turn_scale=20.0, q_mult=2.5),
}


@dataclass(frozen=True)
class Weather:
    rain: float = 0.0
    ice: float = 0.0


def _first(v):
    return v[0] if isinstance(v, (list, tuple)) else v


def _parse_maxspeed(v):
    v = _first(v)
    if v is None:
        return None
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(mph)?", str(v))
    if not m:
        return None
    s = float(m.group(1))
    return s * 1.609344 if m.group(2) else s


def _parse_int(v):
    m = re.match(r"\s*(\d+)", str(_first(v) or ""))
    return int(m.group(1)) if m else None


def _surface_q(d, hw):
    q = 1.0
    s = _first(d.get("surface"))
    if s in SURFACE_Q:
        q = SURFACE_Q[s]
    elif hw == "track":
        q = TRACKTYPE_Q.get(_first(d.get("tracktype")), 1.7)
    return max(q, SMOOTHNESS_Q.get(_first(d.get("smoothness")), 1.0))


def _haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 12742000.0 * math.asin(min(1.0, math.sqrt(a)))


def _bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


class Router:
    def __init__(self, graph, traffic=None, left_hand_traffic=False):
        self.G = graph
        self.traffic = traffic or {}
        self.sign = -1.0 if left_hand_traffic else 1.0
        self._xy = {}
        self._z = {}
        self._bearing = {}
        self._node_delay = {}

    def _pos(self, n):
        p = self._xy.get(n)
        if p is None:
            d = self.G.nodes[n]
            p = self._xy[n] = (float(d["y"]), float(d["x"]))
        return p

    def _elev(self, n):
        z = self._z.get(n)
        if z is None:
            z = self._z[n] = float(self.G.nodes[n].get("elevation", 0.0) or 0.0)
        return z

    def _brg(self, u, v):
        key = (u, v)
        b = self._bearing.get(key)
        if b is None:
            b = self._bearing[key] = _bearing(*self._pos(u), *self._pos(v))
        return b

    def _delay(self, u, m):
        key = (u, m.name)
        val = self._node_delay.get(key)
        if val is None:
            tag = _first(self.G.nodes[u].get("highway"))
            val = float(m.delays.get(tag, 0.0))
            if val == 0.0 and tag is None and len(self.G[u]) >= 3:
                val = float(m.delays.get("junction", 0.0))
            self._node_delay[key] = val
        return val

    def _transition_s(self, prev, u, v, p, m):
        if prev is None:
            return 0.0
        delay = self._delay(u, m) * p.delay_scale
        delta = (self._brg(u, v) - self._brg(prev, u) + 540.0) % 360.0 - 180.0 
        delta *= self.sign
        turn = 0.0
        if abs(delta) >= U_TURN_ANGLE or prev == v:
            turn = U_TURN_S
        elif len(self.G[u]) >= 3 and abs(delta) >= TURN_MIN_ANGLE:
            turn = RIGHT_TURN_S if delta > 0 else LEFT_TURN_S
        return delay + turn * m.turn_scale * p.turn_scale

    def _edge(self, u, v, p, m, w):
        zu, zv = self._elev(u), self._elev(v)
        best = None
        for k, d in self.G[u][v].items():
            hw = _first(d.get("highway"))
            if hw in m.forbidden or d.get("access") in ("no", "private") or d.get(m.access_key) == "no":
                continue
            length = float(d.get("length") or _haversine(*self._pos(u), *self._pos(v)))
            if length <= 0.0:
                length = 0.1
            if m.fixed_speed:
                v_ms = m.cap_kmh / 3.6
            else:
                v_ms = min(_parse_maxspeed(d.get("maxspeed")) or DEFAULT_SPEED_KMH.get(hw, 40), m.cap_kmh) / 3.6
            time_s = length / v_ms

            k_traffic = 1.0
            if m.traffic_aware:
                kt = d.get("k_traffic") or self.traffic.get((u, v, k)) or 1.0
                k_traffic = max(1.0, float(kt)) ** p.traffic_exp

            q = _surface_q(d, hw)
            if q > 1.2:
                q *= 1.0 + 0.6 * w.rain
            q = q ** (m.q_pow * p.q_mult)

            grade = max(-0.3, min(0.3, (zv - zu) / length)) if length > 1.0 else 0.0
            if grade >= 0.0:
                f_hill = 1.0 + m.hill_k * p.hill_mult * grade * 10.0
                if grade > 0.05:
                    f_hill *= 1.0 + 0.4 * w.rain
            else:
                f_hill = max(0.8, 1.0 + 4.0 * grade)

            f_weather = 1.0 + 0.5 * w.ice
            if grade > 0.03:
                f_weather *= 1.0 + w.ice

            f_lane = 1.0
            if m.use_lane_factor:
                f_lane = LANE_FACTOR.get(hw, 1.0)
                lanes = _parse_int(d.get("lanes"))
                if lanes and lanes >= 3:
                    f_lane *= 0.95

            total_time = time_s * k_traffic * q * f_hill * f_weather * f_lane
            cost = p.w_time * total_time + p.w_dist * length + p.w_climb * max(zv - zu, 0.0)
            if p.avoid_tolls and str(_first(d.get("toll"))).lower() == "yes":
                cost += TOLL_PENALTY
            if best is None or cost < best[0]:
                best = (cost, total_time, length)
        return best

    def route(self, source, target, profile="fastest", weather=None, astar=True):
        p = PROFILES[profile] if isinstance(profile, str) else profile
        m = MODES[p.mode]
        w = weather or Weather()
        G = self.G
        if source not in G or target not in G:
            return None

        tlat, tlon = self._pos(target)
        h_scale = p.w_time * HEURISTIC_LB / (m.cap_kmh / 3.6) + p.w_dist

        def h(n):
            if not astar:
                return 0.0
            return _haversine(*self._pos(n), tlat, tlon) * h_scale

        edge_cache = {}
        start = (source, None)
        dist = {start: 0.0}
        parent = {}
        counter = itertools.count()
        heap = [(h(source), 0.0, next(counter), source, None)]
        end_state = None

        while heap:
            _, g, _, u, prev = heapq.heappop(heap)
            state = (u, prev)
            if g > dist.get(state, math.inf):
                continue
            if u == target:
                end_state = state
                break
            for v in G[u]:
                ek = (u, v)
                if ek not in edge_cache:
                    edge_cache[ek] = self._edge(u, v, p, m, w)
                e = edge_cache[ek]
                if e is None:
                    continue
                ng = g + e[0] + p.w_time * self._transition_s(prev, u, v, p, m)
                ns = (v, u)
                if ng < dist.get(ns, math.inf):
                    dist[ns] = ng
                    parent[ns] = state
                    heapq.heappush(heap, (ng + h(v), ng, next(counter), v, u))

        if end_state is None:
            return None

        states = [end_state]
        while states[-1] in parent:
            states.append(parent[states[-1]])
        states.reverse()
        path = [s[0] for s in states]

        total_time = total_len = 0.0
        for i in range(len(path) - 1):
            e = edge_cache.get((path[i], path[i + 1])) or self._edge(path[i], path[i + 1], p, m, w)
            total_time += e[1]
            total_len += e[2]
            prev = path[i - 1] if i > 0 else None
            total_time += self._transition_s(prev, path[i], path[i + 1], p, m)

        return {
            "path": path,
            "cost": dist[end_state],
            "time_s": total_time,
            "distance_m": total_len,
            "coords": [[self._pos(n)[0], self._pos(n)[1]] for n in path],
        }