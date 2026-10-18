import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.http_errors import install_exception_handlers
from app.routers.backup import router as backup_router
from app.routers.devices import router as devices_router
from app.routers.history import router as history_router
from app.routers.meta import router as meta_router
from app.routers.profiles import router as profiles_router
from app.routers.rooms import router as rooms_router
from app.routers.system import router as system_router
from app.services import absence, auto_backup, climate_schedule, dew_point, flow_sensor

# uvicorn only configures its own loggers; without this, app.* messages below
# WARNING would be dropped.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Scheduled heating/cooling switch; its first check runs 30 s after start,
    # so a point missed while the server was off is caught up then.
    climate_schedule.start()
    # Flow temperature via MQTT (only if configured) and the dew point monitor.
    flow_sensor.start()
    dew_point.start()
    auto_backup.start()
    absence.start()
    yield
    absence.stop()
    auto_backup.stop()
    dew_point.stop()
    flow_sensor.stop()
    climate_schedule.stop()


# Served behind nginx at /api (which strips the prefix). root_path makes the
# docs / openapi.json links resolve correctly. Empty for direct local access.
app = FastAPI(
    lifespan=lifespan,
    title="CCU Heating Backend",
    version="2.0.0",
    description="Backend zur Steuerung und Überwachung der HomematicIP CCU3",
    root_path=os.getenv("ROOT_PATH", ""),
)

# CORS: in production the dashboard is same-origin via the nginx proxy, so this
# never triggers. The default covers local dev (frontend :3000 -> uvicorn :8000).
_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_exception_handlers(app)

app.include_router(rooms_router)
app.include_router(profiles_router)
app.include_router(devices_router)
app.include_router(meta_router)
app.include_router(history_router)
app.include_router(backup_router)
app.include_router(system_router, prefix="/system")


@app.get("/")
def root():
    return {"status": "ok", "message": "CCU Heating Backend läuft", "ccu_host": os.getenv("CCU_HOST")}
