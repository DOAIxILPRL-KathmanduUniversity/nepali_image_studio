"""Scalable High-Throughput .np Crawler with Multi-Worker Architecture and Domain Harvester."""
import asyncio
import re
from typing import List, Set, Optional, Dict, Any
from urllib.parse import urljoin, urlparse
import ssl
import httpx
from bs4 import BeautifulSoup
from yarl import URL
from sqlalchemy import select, update, insert, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import CrawlFrontier, CrawlSession, Job, Source, RawAsset, CrawledDomain
from ..database import AsyncSessionLocal
from ..config import settings
from .dedup_service import dedup_service
from .domain_harvester import domain_harvester, NP_DOMAIN_REGEX


def is_allowed_np_domain(url_str: str) -> bool:
    """Strictly allow only .np domains (gov.np, edu.np, org.np, mil.np, net.np, etc.). Reject .com and foreign TLDs."""
    try:
        host = URL(url_str).host
        if not host:
            return False
        host = host.lower()
        return host.endswith(".np")
    except Exception:
        return False


def get_domain_tier(domain: str) -> str:
    """Classify domain tier for prioritization."""
    d = domain.lower()
    if d.endswith(".gov.np"):
        return "gov"
    if d.endswith(".edu.np"):
        return "edu"
    if d.endswith(".org.np"):
        return "org"
    if d.endswith(".mil.np"):
        return "mil"
    if d.endswith(".net.np"):
        return "net"
    return "other"


def get_tier_priority(tier: str) -> int:
    """Map domain tier to job queue priority (1 = highest)."""
    return {"gov": 1, "edu": 2, "org": 3, "mil": 3}.get(tier, 4)


class CrawlerService:
    """
    High-throughput asynchronous crawler with multi-worker concurrency (10-25 workers),
    exhaustive .np domain harvesting, and strict visited tracking.
    """

    def __init__(self):
        self.worker_count: int = settings.CRAWLER_WORKERS  # Default 15
        self.mode: str = "balanced"  # balanced | media_backlog | discovery
        self.active_session_id: Optional[int] = None
        self.is_running: bool = False
        self.is_paused: bool = False
        self._workers: List[asyncio.Task] = []
        self._feeder_task: Optional[asyncio.Task] = None
        self._work_queue: asyncio.Queue = asyncio.Queue(maxsize=150)
        self._domain_locks: Dict[str, asyncio.Semaphore] = {}
        self._domain_failures: Dict[str, int] = {}
        self._slow_domains: Set[str] = set()
        self._client: Optional[httpx.AsyncClient] = None
        self._active_worker_count: int = 0
        self._current_max_depth: int = 4
        self.stats = {
            "pages_crawled": 0,
            "media_found": 0,
            "new_domains_discovered": 0,
            "current_concurrency": 0,
        }

    def _get_domain_lock(self, domain: str) -> asyncio.Semaphore:
        if domain not in self._domain_locks:
            # Maximum 2 concurrent connections per individual domain (polite crawling)
            self._domain_locks[domain] = asyncio.Semaphore(2)
        return self._domain_locks[domain]

    def set_mode(self, mode: str):
        """Set crawler operating mode: balanced, media_backlog, or discovery."""
        if mode not in ("balanced", "media_backlog", "discovery"):
            raise ValueError(f"Invalid mode: {mode}")
        self.mode = mode
        from .queue_service import queue_service
        if mode == "media_backlog":
            # Scale down crawler page concurrency to 5 so bandwidth/CPU prioritize media download
            self.set_concurrency(5)
            queue_service.set_worker_count(25)
        elif mode == "discovery":
            # Maximize crawler page concurrency to 25 for rapid domain and link harvesting
            self.set_concurrency(25)
            queue_service.set_worker_count(8)
        else:  # balanced
            self.set_concurrency(settings.CRAWLER_WORKERS)
            queue_service.set_worker_count(settings.QUEUE_WORKERS)

    async def retry_failed_media_jobs(self) -> int:
        """Reset failed or dead media download/convert jobs back to pending."""
        async with AsyncSessionLocal() as db:
            stmt = update(Job).where(
                Job.status.in_(["dead", "error"]),
                Job.job_type.in_(["download_asset", "convert_pdf", "process_image"])
            ).values(
                status="pending",
                attempts=0,
                error_message=None,
                locked_by=None,
                locked_at=None,
                run_after=func.now(),
            )
            res = await db.execute(stmt)
            await db.commit()
            return res.rowcount

    def reset_circuit_breaker(self) -> int:
        """Clear all slow/throttled domains and reset failure counters."""
        cnt = len(self._slow_domains)
        self._slow_domains.clear()
        self._domain_failures.clear()
        return cnt

    def set_concurrency(self, workers: int):
        """Dynamically adjust worker concurrency (between 5 and 30) on the fly."""
        new_count = max(5, min(workers, 30))
        old_count = self.worker_count
        self.worker_count = new_count
        if self.is_running:
            if new_count > len(self._workers):
                # Scale up coroutine workers immediately
                for i in range(len(self._workers), new_count):
                    t = asyncio.create_task(self._crawler_worker(i, self._current_max_depth))
                    self._workers.append(t)
            elif new_count < len(self._workers):
                # Scale down coroutine workers gracefully
                to_remove = self._workers[new_count:]
                self._workers = self._workers[:new_count]
                for t in to_remove:
                    t.cancel()

    async def start_crawl(
        self,
        session_id: int,
        seed_urls: List[str],
        max_depth: int = 4,
        concurrency: Optional[int] = None,
    ):
        """Start or resume crawl session with multi-worker concurrency."""
        if self.is_running and not self.is_paused:
            return

        self._current_max_depth = max_depth
        if concurrency:
            self.set_concurrency(concurrency)

        self.active_session_id = session_id
        self.is_running = True
        self.is_paused = False

        # Populate frontier with seeds
        async with AsyncSessionLocal() as db:
            for s_url in seed_urls:
                if is_allowed_np_domain(s_url):
                    u_hash = dedup_service.compute_url_hash(s_url)
                    host = URL(s_url).host or ""
                    # Ensure domain is registered
                    if host:
                        await domain_harvester.record_and_seed_domains(db, {host}, discovered_from_url="seed")

                    ins_stmt = pg_insert(CrawlFrontier).values(
                        url=s_url,
                        url_hash=u_hash,
                        domain=host,
                        depth=0,
                        status="pending",
                    ).on_conflict_do_nothing()
                    await db.execute(ins_stmt)

            # Sweep any previously interrupted crawling records back to pending (zero URL loss)
            await db.execute(
                update(CrawlFrontier).where(CrawlFrontier.status == "crawling").values(status="pending")
            )

            stmt_sess = update(CrawlSession).where(CrawlSession.id == session_id).values(
                status="running",
                started_at=func.now()
            )
            await db.execute(stmt_sess)
            await db.commit()

        # Reset circuit breaker
        self._domain_failures.clear()
        self._slow_domains.clear()

        # Shared HTTP Client with connection pooling and fast-track timeout (skip hanging servers)
        headers = {
            "User-Agent": settings.CRAWLER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._client = httpx.AsyncClient(
            headers=headers,
            verify=False,
            timeout=httpx.Timeout(connect=4.0, read=8.0, write=4.0, pool=4.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=120, max_keepalive_connections=40),
        )

        # Launch Feeder Task and Worker Pool
        self._feeder_task = asyncio.create_task(self._frontier_feeder(max_depth))
        self._workers = [
            asyncio.create_task(self._crawler_worker(i, max_depth))
            for i in range(self.worker_count)
        ]

    def pause_crawl(self):
        self.is_paused = True

    def resume_crawl(self):
        self.is_paused = False

    async def stop_crawl(self):
        self.is_running = False
        self.is_paused = False

        if self._feeder_task:
            self._feeder_task.cancel()
            try:
                await self._feeder_task
            except asyncio.CancelledError:
                pass
            self._feeder_task = None

        for w in self._workers:
            w.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()

        if self._client:
            await self._client.aclose()
            self._client = None

        # Drain remaining in-memory queue
        while not self._work_queue.empty():
            try:
                self._work_queue.get_nowait()
                self._work_queue.task_done()
            except Exception:
                break

        if self.active_session_id:
            async with AsyncSessionLocal() as db:
                stmt = update(CrawlSession).where(CrawlSession.id == self.active_session_id).values(
                    status="completed",
                    completed_at=func.now(),
                    stats=self.stats,
                )
                await db.execute(stmt)
                await db.commit()
            self.active_session_id = None

    async def _frontier_feeder(self, max_depth: int):
        """Continuously pulls pending URLs from PostgreSQL frontier into the worker queue."""
        try:
            while self.is_running:
                if self.is_paused or self._work_queue.qsize() > 50:
                    await asyncio.sleep(0.5)
                    continue

                # Mode-based pacing and prioritization:
                # - media_backlog: gentle trickle of 5 URLs every 2.5s (crawler workers stay active crawling, but 85%+ network bandwidth is reserved for media streaming)
                # - balanced: steady stream of 15 URLs every 0.8s for balanced crawl + media download
                # - discovery: max throughput batch of 30 URLs every 0.2s for rapid link & domain harvesting
                if self.mode == "media_backlog":
                    batch_size = 5
                    pace_sleep = 2.5
                elif self.mode == "discovery":
                    batch_size = settings.FRONTIER_BATCH_SIZE
                    pace_sleep = 0.2
                else:  # balanced
                    batch_size = min(15, settings.FRONTIER_BATCH_SIZE)
                    pace_sleep = 0.8

                async with AsyncSessionLocal() as db:
                    # Select batch of pending frontier URLs
                    stmt = select(CrawlFrontier).where(
                        CrawlFrontier.status == "pending",
                        CrawlFrontier.depth <= max_depth,
                    ).order_by(
                        CrawlFrontier.depth.asc(),
                        CrawlFrontier.id.asc()
                    ).limit(batch_size)

                    res = await db.execute(stmt)
                    items = res.scalars().all()

                    if not items:
                        # Queue is momentarily dry, wait before re-checking
                        await asyncio.sleep(2.0)
                        continue

                    # Mark batch as in progress in database
                    for item in items:
                        item.status = "crawling"
                        item.last_attempted_at = func.now()
                        await self._work_queue.put({
                            "id": item.id,
                            "url": item.url,
                            "domain": item.domain,
                            "depth": item.depth,
                        })
                    await db.commit()

                await asyncio.sleep(pace_sleep)
        except asyncio.CancelledError:
            pass

    async def _crawler_worker(self, worker_id: int, max_depth: int):
        """Parallel worker coroutine processing individual page URLs."""
        try:
            while self.is_running:
                if self.is_paused:
                    await asyncio.sleep(0.5)
                    continue

                try:
                    task_data = await asyncio.wait_for(self._work_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                self._active_worker_count += 1
                self.stats["current_concurrency"] = self._active_worker_count

                try:
                    await self._process_page(task_data, max_depth)
                except Exception as e:
                    # Record error on frontier item
                    async with AsyncSessionLocal() as db:
                        stmt = update(CrawlFrontier).where(
                            CrawlFrontier.id == task_data["id"]
                        ).values(status=f"error_{type(e).__name__[:24]}")
                        await db.execute(stmt)
                        await db.commit()
                finally:
                    self._active_worker_count = max(0, self._active_worker_count - 1)
                    self.stats["current_concurrency"] = self._active_worker_count
                    self._work_queue.task_done()

        except asyncio.CancelledError:
            pass

    async def _process_page(self, task_data: dict, max_depth: int):
        """Fetch page HTML, harvest new .np domains, extract images & PDFs, and queue next depth."""
        item_id = task_data["id"]
        url = task_data["url"]
        domain = task_data["domain"]
        depth = task_data["depth"]

        # Fast circuit breaker: immediately skip servers known to be hanging or down
        if domain in self._slow_domains:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(CrawlFrontier).where(CrawlFrontier.id == item_id).values(status="skipped_slow_domain")
                )
                await db.commit()
            return

        lock = self._get_domain_lock(domain)
        async with lock:
            resp = None
            try:
                resp = await self._client.get(url)
            except (httpx.HTTPError, ssl.SSLError) as req_err:
                # If HTTPS fails on legacy Nepal gov servers, try plain HTTP fallback
                if url.startswith("https://"):
                    http_url = "http://" + url[8:]
                    try:
                        resp = await self._client.get(http_url)
                    except Exception:
                        resp = None
            except Exception:
                resp = None

            if resp is None:
                # Track failure count for circuit breaker
                self._domain_failures[domain] = self._domain_failures.get(domain, 0) + 1
                if self._domain_failures[domain] >= 3:
                    self._slow_domains.add(domain)

                async with AsyncSessionLocal() as db:
                    stmt = update(CrawlFrontier).where(CrawlFrontier.id == item_id).values(
                        status="conn_error"
                    )
                    await db.execute(stmt)
                    await db.commit()
                return

            # Reset domain failure count on successful response
            self._domain_failures[domain] = 0

            # Polite delay between requests to the same domain
            await asyncio.sleep(settings.CRAWLER_RATE_LIMIT_MS / 1000.0)

            if resp.status_code != 200:
                async with AsyncSessionLocal() as db:
                    stmt = update(CrawlFrontier).where(CrawlFrontier.id == item_id).values(
                        status=f"http_{resp.status_code}"
                    )
                    await db.execute(stmt)
                    await db.commit()
                return

            html_text = resp.text
            soup = BeautifulSoup(html_text, "html.parser")

            discovered_page_urls: Set[str] = set()
            discovered_media: List[Dict[str, str]] = []

            # 1. Harvest ALL new .np domains mentioned anywhere in the page (text, links, scripts)
            new_domains = domain_harvester.extract_domains_from_text(html_text)

            # 2. Extract links and media from tags (including data-src, srcset for lazyloaded assets)
            for tag in soup.find_all(["a", "img", "iframe", "form", "source", "link"]):
                raw_hrefs = [
                    tag.get("href"),
                    tag.get("src"),
                    tag.get("data-src"),
                    tag.get("data-original"),
                    tag.get("action")
                ]
                # If srcset present, extract individual URLs
                srcset = tag.get("srcset")
                if srcset:
                    for part in srcset.split(","):
                        u_candidate = part.strip().split()[0] if part.strip() else ""
                        if u_candidate:
                            raw_hrefs.append(u_candidate)

                for raw_href in raw_hrefs:
                    if not raw_href or raw_href.startswith(("mailto:", "javascript:", "tel:", "#", "data:")):
                        continue

                    try:
                        resolved = urljoin(url, raw_href)
                        clean_url = str(URL(resolved).with_fragment(None))

                        if not is_allowed_np_domain(clean_url):
                            continue

                        # Harvest domain from resolved URL
                        r_host = URL(clean_url).host
                        if r_host and r_host.lower().endswith(".np"):
                            new_domains.add(r_host.lower())

                        lower_url = clean_url.lower()

                        # Media detection by extension
                        if lower_url.endswith(".pdf"):
                            discovered_media.append({"url": clean_url, "type": "pdf"})
                        elif any(lower_url.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff")):
                            discovered_media.append({"url": clean_url, "type": "image"})
                        elif depth < max_depth:
                            # Page link candidate for next crawl depth
                            discovered_page_urls.add(clean_url)
                    except Exception:
                        continue

            # 3. Content-Type sniffing for attachment links (e.g. download.php?id=123)
            attachment_links = [
                u for u in discovered_page_urls
                if any(k in u.lower() for k in ("download", "attachment", "file_id", "get_file", "view_doc"))
            ][:5]  # Limit to 5 per page to keep it fast

            for a_url in attachment_links:
                try:
                    head_resp = await self._client.head(a_url, timeout=5.0)
                    ctype = head_resp.headers.get("content-type", "").lower()
                    if "pdf" in ctype:
                        discovered_media.append({"url": a_url, "type": "pdf"})
                        discovered_page_urls.discard(a_url)
                    elif "image" in ctype:
                        discovered_media.append({"url": a_url, "type": "image"})
                        discovered_page_urls.discard(a_url)
                except Exception:
                    pass

            # 4. Commit all discoveries into PostgreSQL in a single transaction
            async with AsyncSessionLocal() as db:
                # Mark current URL as done and set crawled_at (NEVER crawled again)
                stmt_done = update(CrawlFrontier).where(CrawlFrontier.id == item_id).values(
                    status="done",
                    crawled_at=func.now()
                )
                await db.execute(stmt_done)

                # Record newly harvested domains
                if new_domains:
                    recorded = await domain_harvester.record_and_seed_domains(
                        db, new_domains, discovered_from_url=url
                    )
                    self.stats["new_domains_discovered"] += len(recorded)

                # Update domain crawled page stats
                tier = get_domain_tier(domain)
                priority = get_tier_priority(tier)
                await db.execute(
                    update(CrawledDomain).where(CrawledDomain.domain == domain).values(
                        pages_crawled=CrawledDomain.pages_crawled + 1,
                        last_crawled_at=func.now()
                    )
                )

                # Enqueue media download jobs into job_queue
                for m in discovered_media:
                    m_hash = dedup_service.compute_url_hash(m["url"])
                    # Check if asset already exists
                    chk = await db.execute(select(RawAsset.id).where(RawAsset.url_hash == m_hash))
                    if not chk.scalar():
                        r_asset = RawAsset(
                            asset_type=m["type"],
                            original_url=m["url"],
                            url_hash=m_hash,
                            status="pending",
                        )
                        db.add(r_asset)
                        await db.flush()

                        # Mode-dependent priority assignment (process_image=1, convert_pdf=2)
                        job_priority = 5
                        if self.mode == "media_backlog":
                            job_priority = 3
                        elif self.mode == "discovery":
                            job_priority = 9

                        job = Job(
                            job_type="download_asset",
                            payload={
                                "raw_asset_id": r_asset.id,
                                "url": m["url"],
                                "asset_type": m["type"],
                                "domain": domain,
                                "tier": tier,
                            },
                            priority=job_priority,
                            status="pending",
                        )
                        db.add(job)

                # Insert next depth page URLs into frontier (strictly ignore if URL hash already exists)
                for page_link in discovered_page_urls:
                    p_hash = dedup_service.compute_url_hash(page_link)
                    p_host = URL(page_link).host or domain
                    front_ins = pg_insert(CrawlFrontier).values(
                        url=page_link,
                        url_hash=p_hash,
                        domain=p_host,
                        depth=depth + 1,
                        discovered_from=url,
                        status="pending",
                    ).on_conflict_do_nothing()
                    await db.execute(front_ins)

                self.stats["pages_crawled"] += 1
                self.stats["media_found"] += len(discovered_media)

                # Live update session stats
                if self.active_session_id:
                    await db.execute(
                        update(CrawlSession).where(CrawlSession.id == self.active_session_id).values(
                            stats=self.stats
                        )
                    )

                await db.commit()


crawler_service = CrawlerService()
