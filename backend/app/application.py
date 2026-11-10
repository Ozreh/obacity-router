"""FastAPI application factory and dependency wiring."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import userdb
from app.api import router as api_router
from auth import router as auth_router
from config import FRONTEND_DIR, get_cors_origins
from services.graph_service import load_boundary, load_graph
from services.routing_service import RoutingService


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        userdb.init_db()
        ring, boundary = load_boundary()
        graph = load_graph()
        app.state.routing_service = RoutingService(graph, ring, boundary)
        print(f"Граф загружен: {len(graph.nodes)} узлов, {len(graph.edges)} рёбер")
        yield

    application = FastAPI(lifespan=lifespan)
    application.include_router(auth_router)
    application.include_router(api_router)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if FRONTEND_DIR.is_dir():
        application.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return application


app = create_app()
