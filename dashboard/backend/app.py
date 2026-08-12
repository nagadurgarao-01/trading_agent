import os
import secrets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from dashboard.backend.telemetry import telemetry_hub
from config.settings import settings

app = FastAPI(title="Trading Agent Performance Dashboard")
security = HTTPBasic()

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(credentials.username, settings.DASHBOARD_USER)
    correct_pass = secrets.compare_digest(credentials.password, settings.DASHBOARD_PASS)
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Global reference to running agent system (injected by main.py)
agent_system_ref = None

# Serve frontend static assets
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(user: str = Depends(authenticate)):
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Trading Agent Dashboard Backend Running</h1>"

@app.get("/api/config")
async def get_config():
    return JSONResponse({
        "env": settings.ENV.lower(),
        "broker": settings.BROKER_TYPE,
        "initial_capital": settings.INITIAL_CAPITAL
    })

@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await telemetry_hub.connect(websocket)
    try:
        while True:
            # Keep socket alive and receive client commands if any
            msg = await websocket.receive_text()
    except WebSocketDisconnect:
        telemetry_hub.disconnect(websocket)

@app.post("/api/kill-switch")
async def execute_kill_switch(user: str = Depends(authenticate)):
    """Emergency endpoint to immediately exit all positions and halt trading."""
    global agent_system_ref
    if agent_system_ref and hasattr(agent_system_ref, "broker"):
        results = agent_system_ref.broker.square_off_all(reason="EMERGENCY_KILL_SWITCH")
        await telemetry_hub.broadcast("LOG_EVENT", {
            "level": "CRITICAL",
            "message": f"🚨 EMERGENCY KILL-SWITCH ACTIVATED by {user}! Exited {len(results)} positions."
        })
        await telemetry_hub.broadcast("POSITIONS_UPDATE", agent_system_ref.broker.get_positions())
        await telemetry_hub.broadcast("METRICS_UPDATE", agent_system_ref.broker.get_account_balance())
        return JSONResponse({"status": "SUCCESS", "exited_positions_count": len(results)})
    return JSONResponse({"status": "WARNING", "message": "Agent broker instance not linked."})
