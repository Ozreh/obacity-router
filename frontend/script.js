const API = 'http://127.0.0.1:8000/route';
const BOUNDARY_API = 'http://127.0.0.1:8000/boundary';
const WALK_SPEED_KMH = 5;

const map = L.map('map', { zoomControl: false }).setView([35.494, 135.748], 14);
L.control.zoom({ position: 'bottomleft' }).addTo(map);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap'
}).addTo(map);

const $ = id => document.getElementById(id);
const els = {
    status: $('status'), summary: $('summary'), dist: $('dist'), time: $('time'),
    coordA: $('coordA'), coordB: $('coordB'), stepA: $('stepA'), stepB: $('stepB'),
    swap: $('swap'), fit: $('fit'), locate: $('locate'), reset: $('reset')
};

// Граница Обамы: рисуем на карте и не даём ставить точки снаружи
let boundaryRing = null; // [[lat, lon], ...]

function insideBoundary(latlng) {
    if (!boundaryRing) return true; // пока граница не загрузилась, не блокируем
    let inside = false;
    for (let i = 0, j = boundaryRing.length - 1; i < boundaryRing.length; j = i++) {
        const [yi, xi] = boundaryRing[i];
        const [yj, xj] = boundaryRing[j];
        if ((yi > latlng.lat) !== (yj > latlng.lat) &&
            latlng.lng < (xj - xi) * (latlng.lat - yi) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
}

fetch(BOUNDARY_API)
    .then(r => r.json())
    .then(data => {
        boundaryRing = data.ring;
        const poly = L.polygon(boundaryRing, {
            color: '#dc2626', weight: 3, fillOpacity: 0, interactive: false
        }).addTo(map);
        map.fitBounds(poly.getBounds());
        map.setMaxBounds(poly.getBounds().pad(0.1)); // карту нельзя увести далеко от Обамы
    })
    .catch(() => {});

const state = { markers: { a: null, b: null }, route: null, controller: null };

const pinIcon = (type, label) => L.divIcon({
    className: '',
    html: `<div class="pin ${type}"><span>${label}</span></div>`,
    iconSize: [30, 30],
    iconAnchor: [4, 30]
});

const fmtCoord = ll => `${ll.lat.toFixed(5)}, ${ll.lng.toFixed(5)}`;

function fmtDist(m) {
    return m < 1000 ? `${Math.round(m)} м` : `${(m / 1000).toFixed(2)} км`;
}

function fmtTime(m) {
    const min = Math.max(1, Math.round(m / 1000 / WALK_SPEED_KMH * 60));
    if (min < 60) return `${min} мин`;
    return `${Math.floor(min / 60)} ч ${min % 60} мин`;
}

function routeLength(coords) {
    let total = 0;
    for (let i = 1; i < coords.length; i++) {
        total += map.distance(coords[i - 1], coords[i]);
    }
    return total;
}

function setStatus(text, isError = false) {
    els.status.textContent = text;
    els.status.classList.toggle('error', isError);
}

function updateSteps() {
    const { a, b } = state.markers;
    els.coordA.textContent = a ? fmtCoord(a.getLatLng()) : 'не выбран';
    els.coordB.textContent = b ? fmtCoord(b.getLatLng()) : 'не выбран';
    els.stepA.classList.toggle('done', !!a);
    els.stepB.classList.toggle('done', !!b);
    els.stepA.classList.toggle('active', !a);
    els.stepB.classList.toggle('active', !!a && !b);
    els.swap.disabled = !(a && b);
}

function clearRoute() {
    if (state.controller) state.controller.abort();
    if (state.route) map.removeLayer(state.route);
    state.route = null;
    els.summary.classList.remove('show');
    els.fit.disabled = true;
}

function addMarker(type, latlng) {
    const marker = L.marker(latlng, {
        draggable: true,
        icon: pinIcon(type, type === 'a' ? 'A' : 'B')
    }).addTo(map);
    marker.on('drag', updateSteps);
    marker.on('dragend', () => {
        updateSteps();
        buildRoute();
    });
    state.markers[type] = marker;
    updateSteps();
}

async function buildRoute() {
    const { a, b } = state.markers;
    if (!a || !b) return;
    clearRoute();
    const s = a.getLatLng();
    const e = b.getLatLng();
    state.controller = new AbortController();
    document.body.classList.add('loading');
    setStatus('Строим маршрут...');
    try {
        const res = await fetch(`${API}?lat1=${s.lat}&lon1=${s.lng}&lat2=${e.lat}&lon2=${e.lng}`, {
            signal: state.controller.signal
        });
        const data = await res.json();
        if (data.error) {
            setStatus(data.error + '. Попробуйте передвинуть точки', true);
            return;
        }
        state.route = L.polyline(data.route, { color: '#2563eb', weight: 6, opacity: .9 }).addTo(map);
        const len = routeLength(data.route);
        els.dist.textContent = fmtDist(len);
        els.time.textContent = fmtTime(len);
        els.summary.classList.add('show');
        els.fit.disabled = false;
        setStatus('Маршрут построен. Точки можно перетаскивать');
        map.fitBounds(state.route.getBounds(), { padding: [60, 60] });
    } catch (err) {
        if (err.name === 'AbortError') return;
        setStatus('Нет связи с сервером. Проверьте, что бэкенд запущен', true);
    } finally {
        document.body.classList.remove('loading');
    }
}

function placePoint(latlng) {
    if (!insideBoundary(latlng)) {
        setStatus('Точка за пределами Обамы', true);
        return;
    }
    if (!state.markers.a) {
        addMarker('a', latlng);
        setStatus('Теперь поставьте финиш');
    } else if (!state.markers.b) {
        addMarker('b', latlng);
        buildRoute();
    }
}

function resetAll() {
    clearRoute();
    Object.keys(state.markers).forEach(k => {
        if (state.markers[k]) map.removeLayer(state.markers[k]);
        state.markers[k] = null;
    });
    updateSteps();
    setStatus('Кликните на карте, чтобы поставить старт');
    document.body.classList.remove('loading');
}

map.on('click', e => placePoint(e.latlng));

els.reset.addEventListener('click', resetAll);

els.fit.addEventListener('click', () => {
    if (state.route) map.fitBounds(state.route.getBounds(), { padding: [60, 60] });
});

els.swap.addEventListener('click', () => {
    const { a, b } = state.markers;
    if (!a || !b) return;
    const pa = a.getLatLng();
    a.setLatLng(b.getLatLng());
    b.setLatLng(pa);
    updateSteps();
    buildRoute();
});

els.locate.addEventListener('click', () => {
    if (!navigator.geolocation) {
        setStatus('Геолокация не поддерживается', true);
        return;
    }
    setStatus('Определяем местоположение...');
    navigator.geolocation.getCurrentPosition(
        pos => {
            const ll = L.latLng(pos.coords.latitude, pos.coords.longitude);
            map.setView(ll, 16);
            placePoint(ll);
        },
        () => setStatus('Не удалось определить местоположение', true),
        { enableHighAccuracy: true, timeout: 10000 }
    );
});

updateSteps();