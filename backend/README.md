# Backend structure

Run from this directory with `uvicorn main:app --reload`.

## Ownership boundaries

- `app/api.py` owns HTTP routes and response contracts. Keep validation and routing algorithms out of this module.
- `services/routing_service.py` owns route use cases and translates bad route requests into `RouteError`.
- `services/graph_service.py` owns OSM filtering, graph construction, cache loading, and boundary geometry loading.
- `router_engine.py` owns the routing algorithm and its domain data (modes, profiles, weather).
- `auth.py` owns authentication endpoints and token/password behavior; `userdb.py` owns persistence.
- `config.py` owns shared paths and environment-backed application configuration.
- `app/application.py` is the composition root: it wires services, middleware, routers, and app lifecycle.

## Working in parallel

Agree on the API contract before changing it. Keep a feature's route, service, and tests in its owning module; avoid editing the composition root for ordinary feature changes. Add new service dependencies through the application state in `app/application.py`, and keep routing-engine changes independent of HTTP concerns. Prefer small feature branches and merge frequently; these boundaries reduce overlapping edits, while normal Git conflict resolution is still needed when two branches touch the same lines.
