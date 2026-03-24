from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routes import events, health, hotspots, priorities, system


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Flashpoint",
    description="Local-first U.S. intelligence dashboard API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten once the frontend origin is known
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(hotspots.router, prefix="/api/v1")
app.include_router(priorities.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
