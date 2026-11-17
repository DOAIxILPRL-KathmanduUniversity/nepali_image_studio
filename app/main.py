"""FastAPI Application entrypoint for Open Nepali Image Platform."""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from .config import settings
from .database import init_db, close_db
from .api import images, crawler, review, search, stats, concepts
from .services.queue_service import queue_service
from .services.crawler_service import crawler_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database tables and start queue worker pool
    await init_db()
    queue_service.start()
    yield
    # Shutdown: stop crawler and queue worker, close database connections
    await crawler_service.stop_crawl()
    await queue_service.stop()
    await close_db()


app = FastAPI(
    title="Open Nepali Image Annotation Platform",
    description="High-throughput multimodal acquisition, OCR & caption annotation system for low-resource Nepali NLP/VLM research.",
    version="1.1.0",
    lifespan=lifespan,
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(stats.router)
app.include_router(images.router)
app.include_router(crawler.router)
app.include_router(review.router)
app.include_router(search.router)
app.include_router(concepts.router)

# Mount static files and modular Jinja2 templates
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """Serve the modular DashCode-inspired annotation platform dashboard."""
    return templates.TemplateResponse(request=request, name="base.html")


@app.get("/health")
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "platform": "Open Nepali Image",
        "version": "1.1.0",
        "crawler_workers": crawler_service.worker_count,
        "queue_workers": queue_service.worker_count,
    }
