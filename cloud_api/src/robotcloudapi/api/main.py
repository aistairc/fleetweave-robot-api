from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers.robots import router as robot_router
from .routers.admin import router as admin_router

app = FastAPI(
    title="Robot Cloud API",
    description="FMS連携API",
    version="v1.0.0"
)
# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(robot_router)
app.include_router(admin_router)
