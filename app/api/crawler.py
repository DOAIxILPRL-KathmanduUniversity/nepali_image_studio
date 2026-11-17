"""API routes for controlling the scalable .np crawler, domain harvester, and concurrency."""
import json
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models import CrawlSession, CrawlFrontier, Job, CrawledDomain
from ..schemas import CrawlStart, CrawlSessionOut
from ..services.crawler_service import crawler_service
from ..config import settings

router = APIRouter(prefix="/api/crawler", tags=["crawler"])


class ConcurrencyUpdate(BaseModel):
    workers: int = Field(ge=5, le=30, default=15)


class CrawlerModeRequest(BaseModel):
    mode: str = Field(pattern="^(balanced|media_backlog|discovery)$")


class CrawlStartEnhanced(BaseModel):
    name: Optional[str] = None
    seed_urls: Optional[list[str]] = None
    max_depth: int = 4
    rate_limit_ms: int = 800
    concurrency: int = Field(ge=5, le=30, default=15)


class SeedTopDomainsRequest(BaseModel):
    tiers: Optional[list[str]] = None  # None for all, or ["gov", "edu", "org", "com"]
    batch_size: int = 100


@router.get("/seeds")
async def get_seed_list():
    """Return categorized .np seed websites (gov.np, edu.np, org.np)."""
    seed_file = Path(__file__).resolve().parent.parent / "seeds" / "nepal_seeds.json"
    if seed_file.exists():
        with open(seed_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"categories": []}


class AddDomainRequest(BaseModel):
    domain_or_url: str


@router.get("/domains")
async def list_harvested_domains(
    tier: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=5, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all unique .np domains discovered and harvested by the crawler with page-by-page controls."""
    stmt = select(CrawledDomain)
    if tier:
        stmt = stmt.where(CrawledDomain.domain_tier == tier)
    if search:
        stmt = stmt.where(CrawledDomain.domain.ilike(f"%{search.strip().lower()}%"))

    # Count filtered
    count_stmt = select(func.count(CrawledDomain.id))
    if tier:
        count_stmt = count_stmt.where(CrawledDomain.domain_tier == tier)
    if search:
        count_stmt = count_stmt.where(CrawledDomain.domain.ilike(f"%{search.strip().lower()}%"))
    total_filtered = (await db.execute(count_stmt)).scalar_one()

    # Pagination
    offset = (page - 1) * limit
    stmt = stmt.order_by(CrawledDomain.pages_crawled.desc(), CrawledDomain.id.desc()).offset(offset).limit(limit)
    res = await db.execute(stmt)
    domains = res.scalars().all()

    # Global Tier counts
    gov_count = (await db.execute(select(func.count(CrawledDomain.id)).where(CrawledDomain.domain_tier == "gov"))).scalar_one()
    edu_count = (await db.execute(select(func.count(CrawledDomain.id)).where(CrawledDomain.domain_tier == "edu"))).scalar_one()
    org_count = (await db.execute(select(func.count(CrawledDomain.id)).where(CrawledDomain.domain_tier == "org"))).scalar_one()
    total_count = (await db.execute(select(func.count(CrawledDomain.id)))).scalar_one()

    total_pages = max(1, (total_filtered + limit - 1) // limit)

    return {
        "page": page,
        "limit": limit,
        "total_filtered": total_filtered,
        "total_pages": total_pages,
        "total_domains": total_count,
        "gov_domains": gov_count,
        "edu_domains": edu_count,
        "org_domains": org_count,
        "domains": [
            {
                "id": d.id,
                "domain": d.domain,
                "domain_tier": d.domain_tier,
                "pages_crawled": d.pages_crawled,
                "status": d.status,
                "discovered_at": d.discovered_at.isoformat() if d.discovered_at else None,
                "last_crawled_at": d.last_crawled_at.isoformat() if d.last_crawled_at else None,
            }
            for d in domains
        ]
    }


@router.post("/domains/add")
async def add_custom_np_domain(
    data: AddDomainRequest,
    db: AsyncSession = Depends(get_db),
):
    """Manually add and seed a new .np domain or portal from the frontend."""
    from ..services.domain_harvester import domain_harvester
    from yarl import URL

    raw = data.domain_or_url.strip()
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = "https://" + raw

    try:
        host = URL(raw).host
        if not host or not host.lower().endswith(".np"):
            raise HTTPException(status_code=400, detail="Domain must end in .np")
        host = host.lower()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid domain or URL format")

    recorded = await domain_harvester.record_and_seed_domains(db, {host}, discovered_from_url="manual_frontend")
    return {
        "domain": host,
        "is_new": len(recorded) > 0,
        "message": f"Domain {host} registered and root seeded into frontier."
    }


@router.post("/start", response_model=CrawlSessionOut)
async def start_crawler(
    data: CrawlStartEnhanced,
    db: AsyncSession = Depends(get_db),
):
    """Start or resume crawl session with chosen .np seeds and worker concurrency."""
    if crawler_service.is_running and not crawler_service.is_paused:
        raise HTTPException(status_code=400, detail="Crawler is already running")

    valid_seeds = []
    if data.seed_urls:
        valid_seeds = [u.strip() for u in data.seed_urls if u.strip().lower().endswith(".np") or ".np/" in u.lower()]

    frontier_pending = (await db.execute(
        select(func.count(CrawlFrontier.id)).where(CrawlFrontier.status == "pending")
    )).scalar_one()

    if not valid_seeds and frontier_pending == 0:
        raise HTTPException(
            status_code=400,
            detail="No seeds provided and no pending items in frontier. Please select seeds or import top .np domains."
        )

    session = CrawlSession(
        name=data.name or f"Crawl {len(valid_seeds) if valid_seeds else frontier_pending} .np targets ({data.concurrency} workers)",
        seed_urls=valid_seeds,
        config={
            "max_depth": data.max_depth,
            "rate_limit_ms": data.rate_limit_ms,
            "concurrency": data.concurrency,
        },
        status="running",
        stats={"pages_crawled": 0, "media_found": 0, "new_domains_discovered": 0},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    await crawler_service.start_crawl(
        session_id=session.id,
        seed_urls=valid_seeds,
        max_depth=data.max_depth,
        concurrency=data.concurrency,
    )

    return session


@router.post("/seed-top-domains")
async def seed_top_domains_api(
    data: SeedTopDomainsRequest = SeedTopDomainsRequest(),
    db: AsyncSession = Depends(get_db),
):
    """Gradually seed the 2,043 .np domains extracted from top10milliondomains.csv."""
    top_file = Path(__file__).resolve().parent.parent / "seeds" / "top_np_domains.json"
    if not top_file.exists():
        raise HTTPException(status_code=404, detail="top_np_domains.json not found. Run scripts/import_np_domains.py first.")

    with open(top_file, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    domains = catalog.get("domains", [])
    if data.tiers:
        allowed = set(t.lower() for t in data.tiers)
        domains = [d for d in domains if d.get("tier") in allowed]

    from ..services.dedup_service import dedup_service
    from ..services.domain_harvester import domain_harvester
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    total_inserted = 0
    total_frontier = 0

    for i in range(0, len(domains), data.batch_size):
        chunk = domains[i : i + data.batch_size]
        for item in chunk:
            dom = item["domain"]
            tier = item["tier"]

            ins_dom = pg_insert(CrawledDomain).values(
                domain=dom,
                domain_tier=tier,
                discovered_from_url="top10milliondomains.csv",
                status="active",
            ).on_conflict_do_nothing(index_elements=["domain"])
            res_d = await db.execute(ins_dom)
            if res_d.rowcount > 0:
                total_inserted += 1

            root_url = f"https://{dom}/"
            url_h = dedup_service.compute_url_hash(root_url)
            ins_f = pg_insert(CrawlFrontier).values(
                url=root_url,
                url_hash=url_h,
                domain=dom,
                depth=0,
                discovered_from="top10milliondomains_seed",
                status="pending",
            ).on_conflict_do_nothing()
            res_f = await db.execute(ins_f)
            if res_f.rowcount > 0:
                total_frontier += 1

        await db.commit()

    return {
        "status": "success",
        "total_catalog": len(domains),
        "new_domains_registered": total_inserted,
        "new_frontier_seeded": total_frontier,
        "message": f"Successfully processed {len(domains)} .np domains into crawler database."
    }


@router.post("/concurrency")
async def set_crawler_concurrency(data: ConcurrencyUpdate):
    """Adjust crawler worker pool concurrency on the fly."""
    crawler_service.set_concurrency(data.workers)
    return {
        "status": "updated",
        "concurrency": crawler_service.worker_count,
        "message": f"Worker concurrency adjusted to {data.workers}"
    }


@router.post("/mode")
async def set_crawler_mode(data: CrawlerModeRequest):
    """Set crawler operating mode: balanced, media_backlog, or discovery."""
    try:
        crawler_service.set_mode(data.mode)
        return {
            "status": "success",
            "mode": crawler_service.mode,
            "crawler_workers": crawler_service.worker_count,
            "message": f"Crawler mode set to {data.mode}"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/media/retry-failed")
async def retry_failed_media():
    """Resets failed or dead media download/convert jobs back to pending."""
    retried_count = await crawler_service.retry_failed_media_jobs()
    return {
        "status": "success",
        "retried_jobs": retried_count,
        "message": f"Successfully requeued {retried_count} failed media jobs"
    }


@router.post("/circuit-breaker/reset")
async def reset_circuit_breaker():
    """Clear all slow or throttled domains from circuit breaker backoff."""
    cleared = crawler_service.reset_circuit_breaker()
    return {
        "status": "success",
        "cleared_domains": cleared,
        "message": f"Circuit breaker reset: {cleared} throttled domains restored"
    }


@router.post("/pause")
async def pause_crawler():
    if not crawler_service.is_running:
        raise HTTPException(status_code=400, detail="Crawler is not currently running")
    crawler_service.pause_crawl()
    return {"status": "paused", "message": "Crawler paused"}


@router.post("/resume")
async def resume_crawler():
    if not crawler_service.is_running:
        raise HTTPException(status_code=400, detail="Crawler is not currently running")
    crawler_service.resume_crawl()
    return {"status": "resumed", "message": "Crawler resumed"}


@router.post("/stop")
async def stop_crawler():
    await crawler_service.stop_crawl()
    return {"status": "stopped", "message": "Crawler stopped"}


@router.get("/status")
async def get_crawler_status(db: AsyncSession = Depends(get_db)):
    """Live status: active workers, frontier counts, media queue, and harvested domains."""
    pending_count = (await db.execute(
        select(func.count(CrawlFrontier.id)).where(CrawlFrontier.status == "pending")
    )).scalar_one()

    crawled_count = (await db.execute(
        select(func.count(CrawlFrontier.id)).where(CrawlFrontier.status == "done")
    )).scalar_one()

    media_jobs_pending = (await db.execute(
        select(func.count(Job.id)).where(Job.status == "pending")
    )).scalar_one()

    media_jobs_processing = (await db.execute(
        select(func.count(Job.id)).where(Job.status == "processing")
    )).scalar_one()

    media_jobs_done = (await db.execute(
        select(func.count(Job.id)).where(Job.status == "done")
    )).scalar_one()

    media_jobs_dead = (await db.execute(
        select(func.count(Job.id)).where(Job.status.in_(["dead", "error"]))
    )).scalar_one()

    domains_count = (await db.execute(
        select(func.count(CrawledDomain.id))
    )).scalar_one()

    latest_sess_stmt = select(CrawlSession).order_by(CrawlSession.id.desc()).limit(1)
    latest_sess = (await db.execute(latest_sess_stmt)).scalars().first()

    from ..services.queue_service import queue_service

    return {
        "is_running": crawler_service.is_running,
        "is_paused": crawler_service.is_paused,
        "mode": crawler_service.mode,
        "active_session_id": crawler_service.active_session_id,
        "worker_count": crawler_service.worker_count,
        "active_workers": crawler_service._active_worker_count,
        "media_workers_count": queue_service.worker_count,
        "media_workers_active": queue_service._active_workers,
        "frontier_pending": pending_count,
        "frontier_crawled": crawled_count,
        "media_jobs_pending": media_jobs_pending,
        "media_jobs_processing": media_jobs_processing,
        "media_jobs_done": media_jobs_done,
        "media_jobs_dead": media_jobs_dead,
        "media_backlog_total": media_jobs_pending + media_jobs_processing,
        "slow_domains_count": len(crawler_service._slow_domains),
        "total_domains_harvested": domains_count,
        "stats": crawler_service.stats,
        "latest_session": {
            "id": latest_sess.id if latest_sess else None,
            "name": latest_sess.name if latest_sess else None,
            "status": latest_sess.status if latest_sess else "idle",
            "stats": latest_sess.stats if latest_sess else {},
        } if latest_sess else None,
    }
