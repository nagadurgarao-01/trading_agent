import re
import os
import secrets
import time
from collections import defaultdict
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from dashboard.backend.telemetry import telemetry_hub
from config.settings import settings
from core.lifecycle import lifecycle_engine

app = FastAPI(title="Trading Agent Performance Dashboard", docs_url=None, redoc_url=None)
security = HTTPBasic()

# In-Memory Rate Limiting against Brute-Force Attacks (IP -> [timestamp, failed_attempts])
failed_auth_attempts = defaultdict(list)
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_PERIOD_SECONDS = 300 # 5 minutes lockout

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Enforces OWASP standard security headers on all HTTP responses."""
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    return response

def authenticate(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Clean up expired timestamps older than 5 minutes
    failed_auth_attempts[client_ip] = [
        t for t in failed_auth_attempts[client_ip] if now - t < LOCKOUT_PERIOD_SECONDS
    ]
    
    # Check if client IP is currently rate-limited
    if len(failed_auth_attempts[client_ip]) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. IP temporarily locked for 5 minutes.",
        )

    correct_user = secrets.compare_digest(credentials.username, settings.DASHBOARD_USER)
    correct_pass = secrets.compare_digest(credentials.password, settings.DASHBOARD_PASS)
    
    if not (correct_user and correct_pass):
        failed_auth_attempts[client_ip].append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Global reference to running agent system (injected by main.py)
agent_system_ref = None
dashboard_sessions = {}

def set_agent_system(system) -> None:
    global agent_system_ref
    agent_system_ref = system

# Serve frontend static assets
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(user: str = Depends(authenticate)):
    index_path = os.path.join(frontend_dir, "index.html")
    session_id = secrets.token_urlsafe(32)
    dashboard_sessions[session_id] = time.time()
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            response = HTMLResponse(f.read())
    else:
        response = HTMLResponse("<h1>Trading Agent Dashboard Backend Running</h1>")
    response.set_cookie("trading_dashboard_session", session_id, httponly=True, samesite="strict", max_age=28800)
    return response

@app.get("/api/config")
async def get_config(user: str = Depends(authenticate)):
    return JSONResponse({
        "env": settings.ENV.lower(),
        "broker": settings.BROKER_TYPE,
        "initial_capital": settings.INITIAL_CAPITAL
    })

@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    session_id = websocket.cookies.get("trading_dashboard_session", "")
    session_created = dashboard_sessions.get(session_id, 0)
    authorized = bool(session_created and time.time() - session_created <= 28800)
    if not authorized:
        await websocket.close(code=1008)
        return
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
        lifecycle_engine.trigger_kill_switch()
        results = agent_system_ref.broker.square_off_all(reason="EMERGENCY_KILL_SWITCH")
        await telemetry_hub.broadcast("LOG_EVENT", {
            "level": "CRITICAL",
            "message": f"🚨 EMERGENCY KILL-SWITCH ACTIVATED by {user}! Exited {len(results)} positions."
        })
        await telemetry_hub.broadcast("POSITIONS_UPDATE", agent_system_ref.broker.get_positions())
        await telemetry_hub.broadcast("METRICS_UPDATE", agent_system_ref.broker.get_account_balance())
        return JSONResponse({"status": "SUCCESS", "exited_positions_count": len(results)})
    return JSONResponse({"status": "WARNING", "message": "Agent broker instance not linked."})

@app.post("/api/positions/{symbol}/close")
async def close_position(symbol: str, user: str = Depends(authenticate)):
    if not re.match(r"^[A-Za-z0-9_.-]{1,30}$", symbol):
        raise HTTPException(status_code=400, detail="Invalid stock symbol format")
    if not agent_system_ref:
        raise HTTPException(status_code=503, detail="Trading system is not ready")
    result = agent_system_ref.broker.close_position(symbol, reason=f"DASHBOARD_MANUAL:{user}")
    return JSONResponse(result)
