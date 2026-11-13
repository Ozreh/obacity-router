const { api, readToken, saveToken, errorText } = Nav;
const REVERSE_URL = `${Nav.API_BASE}/reverse`;
const WALK_SPEED_KMH = 5;
const SLOPE_CLASSES = {
    steep_up: { label: 'Крутой подъём', range: '> 8%', color: '#dc2626' },
    up: { label: 'Подъём', range: '3–8%', color: '#f97316' },
    flat: { label: 'Ровно', range: '±3%', color: '#2563eb' },
    down: { label: 'Спуск', range: '3–8%', color: '#22c55e' },
    steep_down: { label: 'Крутой спуск', range: '> 8%', color: '#0d9488' }
};
const COMMENT_TEXT_MAX = 300;
const COMMENT_REFRESH_MS = 60000;

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
    clearA: $('clearA'), clearB: $('clearB'), waypoints: $('waypoints'),
    addWaypoint: $('addWaypoint'), panel: document.querySelector('.panel'), panelTitle: document.querySelector('.panel h3'),
    profile: $('profile'), swap: $('swap'), fit: $('fit'), locate: $('locate'), reset: $('reset'),
    legend: $('legend'), legendItems: $('legendItems'), legendNote: $('legendNote'), legendElev: $('legendElev'), addComment: $('addComment'),
    userbar: $('userbar'), userName: $('userName'), logout: $('logout'), authLinks: $('authLinks')
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

function loadBoundary() {
    api('/boundary')
        .then(res => {
            if (!res.ok) return;
            boundaryRing = res.data.ring;
            const poly = L.polygon(boundaryRing, {
                color: '#dc2626', weight: 3, fillOpacity: 0, interactive: false
            }).addTo(map);
            map.fitBounds(poly.getBounds());
            map.setMaxBounds(poly.getBounds().pad(0.1)); // карту нельзя увести далеко от Обамы
        })
        .catch(() => {});
}

function logout(expired) {
    saveToken(null);
    location.replace(expired ? 'login.html?reason=expired' : 'login.html');
}

function showMap(user) {
    els.userName.textContent = user.name || user.email;
    els.userbar.classList.add('show');
    document.body.classList.remove('checking');
    setTimeout(() => map.invalidateSize(), 0);
    loadBoundary();
    loadComments();
    setInterval(loadComments, COMMENT_REFRESH_MS);
    setInterval(pruneExpiredComments, 15000);
}

async function bootAuth() {
    if (!readToken()) return logout(false);
    try {
        const me = await api('/auth/me');
        if (me.ok) return showMap(me.data);
        if (me.status === 401) return logout(true);
        document.body.classList.remove('checking');
        els.authLinks.classList.add('show');
        setStatus(errorText(me), true);
    } catch (err) {
        document.body.classList.remove('checking');
        els.authLinks.classList.add('show');
        setStatus(Nav.NO_CONNECTION, true);
    }
}

const state = { markers: { a: null, b: null }, waypoints: [], route: null, controller: null, addingWaypoint: false, addingComment: false };

const pinIcon = (type, label) => L.divIcon({
    className: '',
    html: `<div class="pin ${type}"><span>${label}</span></div>`,
    iconSize: [30, 30],
    iconAnchor: [4, 30]
});

const fmtCoord = ll => `${ll.lat.toFixed(5)}, ${ll.lng.toFixed(5)}`;
const addresses = { a: null, b: null };
const addressRequests = { a: null, b: null };

async function reverseGeocode(type, ll) {
    addressRequests[type]?.abort();
    const controller = new AbortController();
    addressRequests[type] = controller;
    addresses[type] = 'Ищем адрес…';
    updateSteps();
    try {
        const params = new URLSearchParams({ lat: ll.lat, lon: ll.lng });
        const response = await fetch(`${REVERSE_URL}?${params}`, { signal: controller.signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (state.markers[type]?.getLatLng().distanceTo(ll) > 1) return;
        addresses[type] = data.label || null;
    } catch (error) {
        if (error.name === 'AbortError') return;
        addresses[type] = null;
    }
    updateSteps();
}

function fmtDist(m) {
    return m < 1000 ? `${Math.round(m)} м` : `${(m / 1000).toFixed(2)} км`;
}

function fmtTime(m) {
    const min = Math.max(1, Math.round(m / 1000 / WALK_SPEED_KMH * 60));
    if (min < 60) return `${min} мин`;
    return `${Math.floor(min / 60)} ч ${min % 60} мин`;
}

function fmtSeconds(s) {
    const min = Math.max(1, Math.round(s / 60));
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
    els.coordA.textContent = a ? (addresses.a || fmtCoord(a.getLatLng())) : 'не выбран';
    els.coordB.textContent = b ? (addresses.b || fmtCoord(b.getLatLng())) : 'не выбран';
    els.stepA.classList.toggle('done', !!a);
    els.stepB.classList.toggle('done', !!b);
    els.stepA.classList.toggle('active', !a);
    els.stepB.classList.toggle('active', !!a && !b);
    els.clearA.hidden = !a;
    els.clearB.hidden = !b;
    els.swap.disabled = !(a && b);
    els.addWaypoint.disabled = state.waypoints.length >= 8;
    els.addWaypoint.textContent = state.addingWaypoint ? 'Выберите место на карте…' : '+ Остановка';
    renderWaypoints();
}

function renderWaypoints() {
    els.waypoints.innerHTML = '';
    state.waypoints.forEach((waypoint, index) => {
        const row = document.createElement('div');
        row.className = 'waypoint';
        const label = document.createElement('div');
        label.className = 'waypoint-label';
        label.append(`Остановка ${index + 1}`);
        const small = document.createElement('small');
        small.textContent = waypoint.address || fmtCoord(waypoint.marker.getLatLng());
        label.appendChild(small);
        const actions = document.createElement('div');
        actions.className = 'waypoint-actions';
        const up = document.createElement('button');
        up.type = 'button'; up.textContent = '↑'; up.title = 'Переместить выше'; up.disabled = index === 0;
        up.addEventListener('click', () => moveWaypoint(index, index - 1));
        const down = document.createElement('button');
        down.type = 'button'; down.textContent = '↓'; down.title = 'Переместить ниже'; down.disabled = index === state.waypoints.length - 1;
        down.addEventListener('click', () => moveWaypoint(index, index + 1));
        const remove = document.createElement('button');
        remove.type = 'button'; remove.textContent = '×'; remove.title = 'Удалить остановку';
        remove.addEventListener('click', () => removeWaypoint(index));
        actions.append(up, down, remove);
        row.append(label, actions);
        els.waypoints.appendChild(row);
    });
}

function moveWaypoint(from, to) {
    if (to < 0 || to >= state.waypoints.length) return;
    [state.waypoints[from], state.waypoints[to]] = [state.waypoints[to], state.waypoints[from]];
    renumberWaypoints();
    updateSteps();
    buildRoute();
}

function removeWaypoint(index) {
    const [waypoint] = state.waypoints.splice(index, 1);
    map.removeLayer(waypoint.marker);
    addressRequests[waypoint.requestKey]?.abort();
    renumberWaypoints();
    updateSteps();
    buildRoute();
}

function addWaypoint(latlng) {
    const index = state.waypoints.length;
    const waypoint = { marker: null, address: null, requestKey: `w${Date.now()}${index}` };
    const marker = L.marker(latlng, { draggable: true, icon: pinIcon('waypoint', `${index + 1}`) }).addTo(map);
    waypoint.marker = marker;
    marker.on('dragstart', () => { waypoint.address = null; });
    marker.on('drag', updateSteps);
    marker.on('dragend', () => { waypoint.address = null; reverseWaypoint(waypoint); buildRoute(); });
    state.waypoints.push(waypoint);
    reverseWaypoint(waypoint);
    state.addingWaypoint = false;
    updateSteps();
    buildRoute();
}

function renumberWaypoints() {
    state.waypoints.forEach((point, index) => point.marker.setIcon(pinIcon('waypoint', `${index + 1}`)));
}

async function reverseWaypoint(waypoint) {
    addressRequests[waypoint.requestKey]?.abort();
    const controller = new AbortController();
    addressRequests[waypoint.requestKey] = controller;
    const ll = waypoint.marker.getLatLng();
    try {
        const params = new URLSearchParams({ lat: ll.lat, lon: ll.lng });
        const response = await fetch(`${REVERSE_URL}?${params}`, { signal: controller.signal });
        if (!response.ok) return;
        const data = await response.json();
        if (waypoint.marker.getLatLng().distanceTo(ll) > 1) return;
        waypoint.address = data.label || null;
        updateSteps();
    } catch (error) { if (error.name !== 'AbortError') console.warn('Не удалось найти адрес остановки'); }
}

function clearRoute() {
    if (state.controller) state.controller.abort();
    if (state.route) map.removeLayer(state.route);
    state.route = null;
    els.summary.classList.remove('show');
    els.legend.hidden = true;
    els.fit.disabled = true;
}

function addMarker(type, latlng) {
    const marker = L.marker(latlng, {
        draggable: true,
        icon: pinIcon(type, type === 'a' ? 'A' : 'B')
    }).addTo(map);
    marker.on('dragstart', () => { addresses[type] = null; });
    marker.on('drag', updateSteps);
    marker.on('dragend', () => {
        addresses[type] = null;
        updateSteps();
        reverseGeocode(type, marker.getLatLng());
        buildRoute();
    });
    state.markers[type] = marker;
    addresses[type] = null;
    updateSteps();
    reverseGeocode(type, marker.getLatLng());
}

async function buildRoute() {
    const { a, b } = state.markers;
    if (!a || !b) return;
    clearRoute();
    const s = a.getLatLng();
    const e = b.getLatLng();
    const waypoints = state.waypoints.map(point => point.marker.getLatLng());
    const waypointParam = waypoints.length
        ? `&waypoints=${encodeURIComponent(waypoints.map(point => `${point.lat},${point.lng}`).join(';'))}`
        : '';
    state.controller = new AbortController();
    document.body.classList.add('loading');
    setStatus('Строим маршрут...');
    try {
        const res = await api(`/route?lat1=${s.lat}&lon1=${s.lng}&lat2=${e.lat}&lon2=${e.lng}&profile=${els.profile.value}${waypointParam}`, {
            signal: state.controller.signal
        });
        if (res.status === 401) {
            logout(true);
            return;
        }
        const data = res.data || {};
        if (data.error) {
            setStatus(data.error + '. Попробуйте передвинуть точки', true);
            return;
        }
        state.route = drawRoute(data);
        renderLegend(data.slope);
        els.dist.textContent = fmtDist(data.distance_m ?? routeLength(data.route));
        els.time.textContent = fmtSeconds(data.time_s);
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

function drawRoute(data) {
    const group = L.featureGroup();
    L.polyline(data.route, { color: '#fff', weight: 10, opacity: .85, lineJoin: 'round', interactive: false }).addTo(group);
    if (data.slope && data.slope.segments.length) {
        data.slope.segments.forEach(seg => {
            const info = SLOPE_CLASSES[seg.cls];
            L.polyline(seg.coords, { color: info.color, weight: 6, opacity: 1, lineCap: 'butt', lineJoin: 'round' })
                .bindTooltip(`${info.label}: ${seg.grade > 0 ? '+' : ''}${seg.grade}%`, { sticky: true })
                .addTo(group);
        });
    } else {
        L.polyline(data.route, { color: '#2563eb', weight: 6, opacity: .95, lineJoin: 'round' }).addTo(group);
    }
    return group.addTo(map);
}

function renderLegend(slope) {
    els.legendItems.innerHTML = '';
    els.legend.hidden = false;
    if (!slope) {
        els.legendElev.textContent = '';
        els.legendNote.textContent = 'Данные о высотах сейчас недоступны';
        return;
    }
    const used = new Set(slope.segments.map(seg => seg.cls));
    Object.entries(SLOPE_CLASSES).forEach(([key, info]) => {
        if (!used.has(key)) return;
        const row = document.createElement('div');
        row.className = 'legend-item';
        const swatch = document.createElement('i');
        swatch.style.background = info.color;
        const name = document.createElement('span');
        name.textContent = info.label;
        const range = document.createElement('em');
        range.textContent = info.range;
        row.append(swatch, name, range);
        els.legendItems.appendChild(row);
    });
    els.legendElev.textContent = `${slope.min_m}–${slope.max_m} м`;
    els.legendNote.textContent = `Набор высоты +${slope.gain_m} м · спуск −${slope.loss_m} м`;
}

function placePoint(latlng) {
    if (!insideBoundary(latlng)) {
        setStatus('Точка за пределами Обамы', true);
        return;
    }
    if (state.addingComment) {
        setCommentMode(false);
        openCommentEditor(latlng);
    } else if (state.addingWaypoint) {
        addWaypoint(latlng);
    } else if (!state.markers.a) {
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
        addresses[k] = null;
        addressRequests[k]?.abort();
    });
    state.waypoints.forEach(point => map.removeLayer(point.marker));
    state.waypoints = [];
    state.addingWaypoint = false;
    updateSteps();
    setStatus('Кликните на карте, чтобы поставить старт');
    document.body.classList.remove('loading');
}

function clearPoint(type) {
    const marker = state.markers[type];
    if (!marker) return;
    map.removeLayer(marker);
    state.markers[type] = null;
    addresses[type] = null;
    addressRequests[type]?.abort();
    if (type === 'a') {
        state.waypoints.forEach(point => map.removeLayer(point.marker));
        state.waypoints = [];
        state.addingWaypoint = false;
    }
    clearRoute();
    updateSteps();
    setStatus(type === 'a'
        ? (state.markers.b ? 'Старт удалён. Выберите новый старт' : 'Старт удалён. Кликните на карте, чтобы поставить старт')
        : 'Финиш удалён. Выберите новый финиш');
    if (state.markers.a && state.markers.b) buildRoute();
}

const commentPins = new Map();
const commentIcon = mine => L.divIcon({
    className: '',
    html: `<div class="cmt-pin${mine ? ' mine' : ''}"><span>💬</span></div>`,
    iconSize: [34, 34],
    iconAnchor: [6, 34],
    popupAnchor: [10, -34]
});

function setCommentMode(on) {
    state.addingComment = on;
    els.addComment.classList.toggle('active-mode', on);
    els.addComment.textContent = on ? 'Кликните на карте… (отмена)' : '💬 Оставить комментарий';
    if (on) {
        state.addingWaypoint = false;
        updateSteps();
        setStatus('Кликните на карте там, где хотите оставить комментарий');
    }
}

function fmtLeft(expiresAt) {
    const sec = Math.max(0, expiresAt - Date.now() / 1000);
    const min = Math.ceil(sec / 60);
    if (min < 60) return `${min} мин`;
    return `${Math.floor(min / 60)} ч ${min % 60} мин`;
}

function removeCommentPin(id) {
    const pin = commentPins.get(id);
    if (!pin) return;
    map.removeLayer(pin.marker);
    commentPins.delete(id);
}

function commentPopupContent(comment) {
    const box = document.createElement('div');
    box.className = 'cmt-popup';
    const author = document.createElement('div');
    author.className = 'cmt-author';
    author.textContent = comment.mine ? 'Вы' : comment.author;
    const text = document.createElement('div');
    text.className = 'cmt-text';
    text.textContent = comment.text;
    const left = document.createElement('div');
    left.className = 'cmt-left';
    left.textContent = `Исчезнет через ${fmtLeft(comment.expires_at)}`;
    box.append(author, text, left);
    if (comment.mine) {
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = 'Удалить';
        remove.addEventListener('click', async () => {
            remove.disabled = true;
            try {
                const res = await api(`/comments/${comment.id}`, { method: 'DELETE' });
                if (res.status === 401) return logout(true);
                if (res.ok || res.status === 404) removeCommentPin(comment.id);
                else {
                    remove.disabled = false;
                    setStatus(errorText(res), true);
                }
            } catch (err) {
                remove.disabled = false;
                setStatus(Nav.NO_CONNECTION, true);
            }
        });
        box.appendChild(remove);
    }
    return box;
}

function upsertCommentPin(comment) {
    const existing = commentPins.get(comment.id);
    if (existing) {
        existing.data = comment;
        existing.marker.setPopupContent(commentPopupContent(comment));
        return;
    }
    const marker = L.marker([comment.lat, comment.lon], { icon: commentIcon(comment.mine) }).addTo(map);
    marker.bindPopup(() => commentPopupContent(commentPins.get(comment.id).data), { minWidth: 230, maxWidth: 260 });
    commentPins.set(comment.id, { data: comment, marker });
}

function pruneExpiredComments() {
    const now = Date.now() / 1000;
    commentPins.forEach((pin, id) => {
        if (pin.data.expires_at <= now) removeCommentPin(id);
    });
}

async function loadComments() {
    try {
        const res = await api('/comments');
        if (res.status === 401) return logout(true);
        if (!res.ok || !Array.isArray(res.data)) return;
        const alive = new Set(res.data.map(comment => comment.id));
        [...commentPins.keys()].forEach(id => { if (!alive.has(id)) removeCommentPin(id); });
        res.data.forEach(upsertCommentPin);
    } catch (err) {}
}

function openCommentEditor(latlng) {
    if (!insideBoundary(latlng)) {
        setStatus('Точка за пределами Обамы', true);
        return;
    }
    const box = document.createElement('div');
    box.className = 'cmt-popup';
    const area = document.createElement('textarea');
    area.maxLength = COMMENT_TEXT_MAX;
    area.placeholder = 'Что здесь важно знать? Исчезнет через 24 часа';
    const row = document.createElement('div');
    row.className = 'cmt-row';
    const count = document.createElement('span');
    count.className = 'cmt-count';
    count.textContent = `0/${COMMENT_TEXT_MAX}`;
    const send = document.createElement('button');
    send.type = 'button';
    send.className = 'primary';
    send.textContent = 'Опубликовать';
    row.append(count, send);
    const error = document.createElement('div');
    error.className = 'cmt-error';
    box.append(area, row, error);
    area.addEventListener('input', () => { count.textContent = `${area.value.length}/${COMMENT_TEXT_MAX}`; });
    send.addEventListener('click', async () => {
        const text = area.value.trim();
        if (!text) {
            error.textContent = 'Введите текст комментария';
            return;
        }
        send.disabled = true;
        error.textContent = '';
        try {
            const res = await api('/comments', { method: 'POST', body: { lat: latlng.lat, lon: latlng.lng, text } });
            if (res.status === 401) return logout(true);
            if (!res.ok) {
                error.textContent = errorText(res);
                send.disabled = false;
                return;
            }
            map.closePopup(popup);
            upsertCommentPin(res.data);
            setStatus('Комментарий добавлен. Он исчезнет через 24 часа');
        } catch (err) {
            error.textContent = Nav.NO_CONNECTION;
            send.disabled = false;
        }
    });
    const popup = L.popup({ minWidth: 230, maxWidth: 260, closeOnClick: false }).setLatLng(latlng).setContent(box).openOn(map);
    setTimeout(() => area.focus(), 0);
}

map.on('click', e => placePoint(e.latlng));
map.on('contextmenu', e => {
    setCommentMode(false);
    openCommentEditor(e.latlng);
});
els.addComment.addEventListener('click', () => setCommentMode(!state.addingComment));

els.reset.addEventListener('click', resetAll);
els.addWaypoint.addEventListener('click', () => {
    if (state.waypoints.length >= 8) return;
    state.addingWaypoint = !state.addingWaypoint;
    if (state.addingWaypoint) setCommentMode(false);
    updateSteps();
    setStatus(state.addingWaypoint ? 'Кликните на карте, чтобы добавить остановку' : 'Добавление остановки отменено');
});
els.clearA.addEventListener('click', () => clearPoint('a'));
els.clearB.addEventListener('click', () => clearPoint('b'));

els.profile.addEventListener('change', buildRoute);

els.logout.addEventListener('click', () => logout(false));

els.fit.addEventListener('click', () => {
    if (state.route) map.fitBounds(state.route.getBounds(), { padding: [60, 60] });
});

els.swap.addEventListener('click', () => {
    const { a, b } = state.markers;
    if (!a || !b) return;
    const orderedPoints = [{ marker: a, address: addresses.a },
        ...state.waypoints.map(point => ({ marker: point.marker, address: point.address })),
        { marker: b, address: addresses.b }].reverse();
    const [newStart, ...rest] = orderedPoints;
    const newFinish = rest.pop();
    const [newA, newB] = [newStart.marker, newFinish.marker];
    state.markers.a = newA;
    state.markers.b = newB;
    addresses.a = newStart.address;
    addresses.b = newFinish.address;
    state.waypoints = rest.map(point => ({ ...point, requestKey: `w${Date.now()}${Math.random()}` }));
    state.waypoints.forEach((point, index) => {
        point.marker.setIcon(pinIcon('waypoint', `${index + 1}`));
    });
    newA.setIcon(pinIcon('a', 'A'));
    newB.setIcon(pinIcon('b', 'B'));
    reverseGeocode('a', newA.getLatLng());
    reverseGeocode('b', newB.getLatLng());
    state.waypoints.forEach(point => reverseWaypoint(point));
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

// Drag the route panel from empty space, without hijacking interactive controls.
let panelDrag = null;
els.panel.addEventListener('pointerdown', event => {
    if (event.target.closest('button, a, input, select, textarea, .step, .waypoint, .userbar')) return;
    const rect = els.panel.getBoundingClientRect();
    panelDrag = { pointerId: event.pointerId, x: event.clientX - rect.left, y: event.clientY - rect.top };
    event.preventDefault();
    if (!els.panel.style.left) {
        els.panel.style.left = `${rect.left}px`;
        els.panel.style.top = `${rect.top}px`;
        els.panel.style.right = 'auto';
        els.panel.style.bottom = 'auto';
    }
    els.panel.setPointerCapture(event.pointerId);
    els.panel.classList.add('dragging');
});
els.panel.addEventListener('pointermove', event => {
    if (!panelDrag || panelDrag.pointerId !== event.pointerId) return;
    const left = Math.max(0, Math.min(innerWidth - els.panel.offsetWidth, event.clientX - panelDrag.x));
    const top = Math.max(0, Math.min(innerHeight - els.panel.offsetHeight, event.clientY - panelDrag.y));
    Object.assign(els.panel.style, { left: `${left}px`, top: `${top}px`, right: 'auto', bottom: 'auto' });
});
const stopPanelDrag = event => {
    if (!panelDrag || panelDrag.pointerId !== event.pointerId) return;
    panelDrag = null;
    els.panel.classList.remove('dragging');
};
els.panel.addEventListener('pointerup', stopPanelDrag);
els.panel.addEventListener('pointercancel', stopPanelDrag);
function setPointFromSearch(item) {
    const ll = L.latLng(item.lat, item.lon);
    if (!insideBoundary(ll)) {
        setStatus('Адрес за пределами Обамы', true);
        return;
    }
    const { a, b } = state.markers;
    if (!a) {
        map.flyTo(ll, 17, { duration: 0.8 });
        addMarker('a', ll);
        setStatus('Старт выбран. Теперь выберите финиш');
    } else if (!b) {
        addMarker('b', ll);
        buildRoute();
    } else {
        b.setLatLng(ll);
        updateSteps();
        reverseGeocode('b', ll);
        buildRoute();
    }
}

els.panelTitle.addEventListener('dblclick', () => {
    els.panel.style.left = '';
    els.panel.style.top = '';
    els.panel.style.right = '';
    els.panel.style.bottom = '';
});

initSearchBox(map, {
    input: $('search-input'),
    list: $('search-results'),
    clearButton: $('search-clear'),
    onSelect: setPointFromSearch
});

updateSteps();
bootAuth();
