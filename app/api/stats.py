"""API routes for system metrics, disk health, and annotation progress."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models import Image as ImageModel, CrawlSession, Job
from ..schemas import DashboardStats
from ..services.cleanup_service import cleanup_service

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Aggregate high-level metrics for dashboard header and status widgets."""
    # Counts by status
    total_imgs = (await db.execute(select(func.count(ImageModel.id)))).scalar_one()

    pending_imgs = (await db.execute(
        select(func.count(ImageModel.id)).where(ImageModel.status == "ready")
    )).scalar_one()

    approved_imgs = (await db.execute(
        select(func.count(ImageModel.id)).where(ImageModel.is_approved == True)
    )).scalar_one()

    annotated_imgs = (await db.execute(
        select(func.count(ImageModel.id)).where(ImageModel.annotation_text.isnot(None))
    )).scalar_one()

    skipped_imgs = (await db.execute(
        select(func.count(ImageModel.id)).where(ImageModel.status == "skipped")
    )).scalar_one()

    ai_pending = (await db.execute(
        select(func.count(ImageModel.id)).where(
            ImageModel.annotation_source == "ai_pending",
            ImageModel.is_approved == False
        )
    )).scalar_one()

    total_crawls = (await db.execute(select(func.count(CrawlSession.id)))).scalar_one()
    active_crawls = (await db.execute(
        select(func.count(CrawlSession.id)).where(CrawlSession.status == "running")
    )).scalar_one()

    queue_depth = (await db.execute(
        select(func.count(Job.id)).where(Job.status == "pending")
    )).scalar_one()

    disk_info = cleanup_service.get_disk_stats()

    return DashboardStats(
        total_images=total_imgs,
        pending_images=pending_imgs,
        annotated_images=annotated_imgs,
        approved_images=approved_imgs,
        skipped_images=skipped_imgs,
        ai_pending_review=ai_pending,
        total_crawl_sessions=total_crawls,
        active_crawls=active_crawls,
        queue_depth=queue_depth,
        disk_usage_gb=disk_info["used_gb"],
        disk_free_gb=disk_info["free_gb"],
    )


@router.get("/network")
async def get_network_info():
    """Discover local Wi-Fi / LAN IP address for mobile phone / router access."""
    import socket
    lan_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    return {
        "lan_ip": lan_ip,
        "port": 8000,
        "phone_url": f"http://{lan_ip}:8000",
        "qr_api_url": f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=http://{lan_ip}:8000"
    }
