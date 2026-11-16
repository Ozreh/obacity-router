const SEARCH_URL = `${Nav.API_BASE}/search`;

const debounce = (fn, delay) => {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
};

function initSearchBox(map, { input, list, clearButton, categoryButtons, onSelect }) {
  let controller = null;
  const poiLayer = L.layerGroup().addTo(map);
  const poiMarkers = new Map();
  let visiblePlaces = [];
  let items = [];
  let active = -1;
  let requestNumber = 0;

  const updateClearButton = () => {
    if (clearButton) clearButton.hidden = !input.value;
  };

  const poiPopup = (item) => {
    const box = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = item.label;
    box.appendChild(title);
    if (item.brand && !item.label.includes(item.brand)) {
      const brand = document.createElement("div");
      brand.textContent = item.brand;
      box.appendChild(brand);
    }
    if (item.opening_hours) {
      const hours = document.createElement("div");
      hours.textContent = `Часы: ${item.opening_hours}`;
      box.appendChild(hours);
    }
    if (item.phone) {
      const phone = document.createElement("div");
      phone.textContent = `Телефон: ${item.phone}`;
      box.appendChild(phone);
    }
    if (/^https?:\/\//i.test(item.website || "")) {
      const link = document.createElement("a");
      link.href = item.website;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "Сайт";
      box.appendChild(link);
    }
    return box;
  };

  const redrawPlaceMarkers = () => {
    poiLayer.clearLayers();
    poiMarkers.clear();
    const icons = {
      coffee: "☕", ramen: "🍜", restaurant: "🍽", shopping: "🛍", convenience: "🏪",
      supermarket: "🛒", healthcare: "🏥", pharmacy: "💊", transport: "🚌", money: "🏧",
      education: "🎓", public: "🚻", religion: "⛩", stay: "🏨", leisure: "🌳",
      culture: "🏛", services: "🛁", office: "🏢", building: "📍", landuse: "🗺"
    };
    visiblePlaces.forEach((item) => {
      const icon = L.divIcon({
        className: "poi-map-icon",
        html: `<span>${icons[item.kind] || "📍"}</span>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16]
      });
      const poiMarker = L.marker([item.lat, item.lon], { icon }).addTo(poiLayer);
      poiMarker.bindPopup(poiPopup(item));
      poiMarkers.set(item.id, poiMarker);
    });
  };

  const hide = () => {
    list.hidden = true;
    list.innerHTML = "";
    items = [];
    active = -1;
  };

  const select = (item) => {
    input.value = item.label;
    updateClearButton();
    hide();
    if (item.kind) {
      map.flyTo([item.lat, item.lon], 17, { duration: 0.8 });
      poiMarkers.get(item.id)?.openPopup();
      return;
    }
    if (onSelect) {
      onSelect(item);
      return;
    }
    map.flyTo([item.lat, item.lon], 18, { duration: 0.8 });
  };

  const render = (results) => {
    const suggestions = results.slice(0, 12);
    items = suggestions;
    active = -1;
    list.innerHTML = "";
    visiblePlaces = results.filter((item) => item.kind);
    suggestions.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item.label;
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        select(item);
      });
      list.appendChild(li);
    });
    redrawPlaceMarkers();
    list.hidden = suggestions.length === 0;
  };

  const restorePlaceMarkers = () => {
    if (visiblePlaces.length && poiLayer.getLayers().length === 0) redrawPlaceMarkers();
  };
  map.on("moveend zoomend", restorePlaceMarkers);

  const highlight = () => {
    [...list.children].forEach((li, i) => li.classList.toggle("active", i === active));
  };

  const fetchSuggestions = async (q, category = "") => {
    const currentRequest = ++requestNumber;
    if (controller) controller.abort();
    controller = new AbortController();
    const center = map.getCenter();
    const params = new URLSearchParams({ q, limit: category ? "500" : "8", lat: center.lat, lon: center.lng });
    if (category) params.set("category", category);
    try {
      const res = await fetch(`${SEARCH_URL}?${params}`, { signal: controller.signal });
      if (!res.ok) throw new Error(res.status);
      const results = await res.json();
      if (currentRequest === requestNumber && input.value.trim() === q) render(results);
    } catch (e) {
      if (e.name !== "AbortError" && currentRequest === requestNumber) hide();
    }
  };

  const debounced = debounce(fetchSuggestions, 250);

  categoryButtons?.forEach((button) => button.addEventListener("click", () => {
    const category = button.dataset.category;
    input.value = button.dataset.query || button.textContent.trim();
    updateClearButton();
    if (controller) controller.abort();
    requestNumber++;
    poiLayer.clearLayers();
    poiMarkers.clear();
    visiblePlaces = [];
    fetchSuggestions(input.value.trim(), category);
  }));

  input.addEventListener("input", () => {
    updateClearButton();
    const q = input.value.trim();
    if (!q) {
      if (controller) controller.abort();
      hide();
      poiLayer.clearLayers();
      poiMarkers.clear();
      return;
    }
    poiLayer.clearLayers();
    poiMarkers.clear();
    visiblePlaces = [];
    debounced(q);
  });

  input.addEventListener("focus", () => input.select());

  clearButton?.addEventListener("click", () => {
    if (controller) controller.abort();
    requestNumber++;
    input.value = "";
    hide();
    updateClearButton();
    poiLayer.clearLayers();
    poiMarkers.clear();
    visiblePlaces = [];
    input.focus();
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!items.length) return;
      const step = e.key === "ArrowDown" ? 1 : -1;
      active = (active + step + items.length) % items.length;
      highlight();
    } else if (e.key === "Enter" && items.length) {
      e.preventDefault();
      select(items[active >= 0 ? active : 0]);
    } else if (e.key === "Escape") {
      hide();
    }
  });

  input.addEventListener("blur", hide);
  updateClearButton();
}
