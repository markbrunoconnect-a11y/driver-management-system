from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import Base, engine
from app.routers import auth, tickets, vehicles
import os

app = FastAPI(title="Driver Management System")

# Create all tables on startup
Base.metadata.create_all(bind=engine)

# Routers
app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(vehicles.router)

# Serve frontend
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
def serve_app():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/{full_path:path}")
def catch_all(full_path: str):
    if full_path.startswith("api/"):
        return {"detail": "Not found"}
    return FileResponse(os.path.join(frontend_dir, "index.html"))
