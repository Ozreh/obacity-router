const SEARCH_URL = "http://127.0.0.1:8000/search";

const debounce = (fn, delay) => {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
};

function initSearchBox(map, { input, list, clearButton, onSelect }) {
  let controller = null;
  let marker = null;
  let items = [];
  let active = -1;
  let requestNumber = 0;

  const updateClearButton = () => {
    if (clearButton) clearButton.hidden = !input.value;
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
    if (onSelect) {
      onSelect(item);
      return;
    }
    map.flyTo([item.lat, item.lon], 18, { duration: 0.8 });
    if (marker) marker.remove();
    marker = L.marker([item.lat, item.lon]).addTo(map).bindPopup(item.label).openPopup();
  };

  const render = (results) => {
    items = results;
    active = -1;
    list.innerHTML = "";
    results.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item.label;
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        select(item);
      });
      list.appendChild(li);
    });
    list.hidden = results.length === 0;
  };

  const highlight = () => {
    [...list.children].forEach((li, i) => li.classList.toggle("active", i === active));
  };

  const fetchSuggestions = async (q) => {
    const currentRequest = ++requestNumber;
    if (controller) controller.abort();
    controller = new AbortController();
    const center = map.getCenter();
    const params = new URLSearchParams({ q, limit: "8", lat: center.lat, lon: center.lng });
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

  input.addEventListener("input", () => {
    updateClearButton();
    const q = input.value.trim();
    if (!q) {
      if (controller) controller.abort();
      hide();
      return;
    }
    debounced(q);
  });

  input.addEventListener("focus", () => input.select());

  clearButton?.addEventListener("click", () => {
    if (controller) controller.abort();
    requestNumber++;
    input.value = "";
    hide();
    updateClearButton();
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
