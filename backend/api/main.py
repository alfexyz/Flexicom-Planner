"""
Flexicom Planner — FastAPI application.

Start with:
    uvicorn backend.api.main:app --reload --port 8000

Interactive docs: http://localhost:8000/docs
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routers import alerts, customers, forecast, overview, products, upload

app = FastAPI(
    title       = "Flexicom Planner API",
    description = "S&OP platform for Romanian SMBs — demand, inventory, margin, and customer analytics.",
    version     = "0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],   # tighten in production
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(overview.router)
app.include_router(products.router)
app.include_router(alerts.router)
app.include_router(customers.router)
app.include_router(upload.router)
app.include_router(forecast.router)


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
