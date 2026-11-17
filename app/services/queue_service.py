"""Queue Worker Pool: Executes background ingestion and media jobs concurrently via SKIP LOCKED."""
import asyncio
import os
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional, List
import httpx
from sqlalchemy import text, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Job, RawAsset, Image as ImageModel
from ..database import AsyncSessionLocal
from ..config import settings
from .image_service import image_service
from .pdf_service import pdf_service
from .dedup_service import dedup_service
from .cleanup_service import cleanup_service


# Standalone worker functions for ProcessPoolExecutor (must be top-level pickleable)
def _process_image_cpu_worker(image_path: str, out_dir: str, tier: str) -> Optional[dict]:
    """Execute A4-max resizing, WebP compression, and perceptual hashing in worker subprocess."""
    return image_service.process_and_compress(
        input_path=image_path,
        output_dir=out_dir,
        filename_prefix=tier,
    )


def _convert_pdf_cpu_worker(pdf_path: str, temp_dir: str, max_pages: int) -> list:
    """Execute PyMuPDF page rendering in worker subprocess."""
    return pdf_service.extract_pages(pdf_path, temp_dir, max_pages=max_pages)


class QueueService:
    """Consumes and executes pipeline jobs with concurrent coroutines and CPU process pooling."""

    def __init__(self):
        self.worker_count: int = settings.QUEUE_WORKERS  # Default 15
        self.worker_id_prefix: str = f"qw_{uuid.uuid4().hex[:6]}"
        self.is_running: bool = False
        self._worker_tasks: List[asyncio.Task] = []
        self._cpu_executor: Optional[ProcessPoolExecutor] = None
        self._active_workers: int = 0

    def start(self):
        """Start the background queue worker pool and CPU process executor."""
        if self.is_running:
            return
        self.is_running = True
        self._cpu_executor = ProcessPoolExecutor(max_workers=settings.CPU_PROCESS_WORKERS)
        self._worker_tasks = [
            asyncio.create_task(self._worker_loop(f"{self.worker_id_prefix}_{i}"))
            for i in range(self.worker_count)
        ]
        asyncio.create_task(self._periodic_reaper())

    async def _periodic_reaper(self):
        """Periodically reset jobs stuck in 'processing' state back to pending."""
        while self.is_running:
            try:
                await self.reap_stuck_jobs()
            except Exception:
                pass
            await asyncio.sleep(60.0)

    async def reap_stuck_jobs(self):
        """Reset jobs stuck in processing state for >10 minutes back to pending."""
        async with AsyncSessionLocal() as db:
            stmt = text("""
                UPDATE job_queue
                SET status = 'pending', locked_by = NULL, locked_at = NULL
                WHERE status = 'processing' AND locked_at < NOW() - INTERVAL '10 minutes'
            """)
            await db.execute(stmt)
            await db.commit()

    def set_worker_count(self, count: int):
        """Dynamically scale queue worker coroutines (5 to 30) on the fly."""
        new_count = max(5, min(count, 30))
        self.worker_count = new_count
        if self.is_running:
            if new_count > len(self._worker_tasks):
                for i in range(len(self._worker_tasks), new_count):
                    t = asyncio.create_task(self._worker_loop(f"{self.worker_id_prefix}_{i}"))
                    self._worker_tasks.append(t)
            elif new_count < len(self._worker_tasks):
                to_cancel = self._worker_tasks[new_count:]
                self._worker_tasks = self._worker_tasks[:new_count]
                for t in to_cancel:
                    t.cancel()

    async def stop(self):
        """Stop all workers and shutdown process executor."""
        self.is_running = False
        for t in self._worker_tasks:
            t.cancel()
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            self._worker_tasks.clear()

        if self._cpu_executor:
            self._cpu_executor.shutdown(wait=False)
            self._cpu_executor = None

    def _is_low_memory(self) -> bool:
        """Check if system available RAM is below safety threshold."""
        try:
            import psutil
            avail_mb = psutil.virtual_memory().available / (1024 * 1024)
            return avail_mb < settings.MEMORY_SAFETY_THRESHOLD_MB
        except Exception:
            return False

    async def _worker_loop(self, worker_tag: str):
        """Individual worker coroutine polling job_queue with FOR UPDATE SKIP LOCKED."""
        while self.is_running:
            try:
                # Memory safety pause
                if self._is_low_memory():
                    await asyncio.sleep(2.0)
                    continue

                job_executed = await self._fetch_and_execute_job(worker_tag)
                if not job_executed:
                    # Queue is empty, polite poll delay
                    await asyncio.sleep(settings.QUEUE_POLL_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)

    async def _fetch_and_execute_job(self, worker_tag: str) -> bool:
        """Fetch one job atomically using SKIP LOCKED."""
        job_id = None
        job_type = None
        payload = {}

        async with AsyncSessionLocal() as db:
            fetch_query = text("""
                UPDATE job_queue
                SET status = 'processing', locked_by = :w_id, locked_at = NOW(), attempts = attempts + 1
                WHERE id = (
                    SELECT id FROM job_queue
                    WHERE status = 'pending' AND run_after <= NOW()
                    ORDER BY priority ASC, created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id, job_type, payload, attempts, max_attempts;
            """)
            res = await db.execute(fetch_query, {"w_id": worker_tag})
            row = res.mappings().first()
            if not row:
                return False

            job_id = row["id"]
            job_type = row["job_type"]
            payload = row["payload"]
            attempts = row["attempts"]
            max_attempts = row["max_attempts"]
            await db.commit()

        self._active_workers += 1
        err_msg = None
        try:
            if job_type == "download_asset":
                await self._handle_download_asset(payload)
            elif job_type == "convert_pdf":
                await self._handle_convert_pdf(payload)
            elif job_type == "process_image":
                await self._handle_process_image(payload)
            elif job_type == "cleanup":
                async with AsyncSessionLocal() as db:
                    await cleanup_service.cleanup_skipped_files(db)
                    await cleanup_service.cleanup_raw_assets(db)
        except Exception as e:
            err_msg = str(e)
        finally:
            self._active_workers = max(0, self._active_workers - 1)

        # Update job outcome
        async with AsyncSessionLocal() as db:
            if err_msg:
                new_status = "dead" if attempts >= max_attempts else "pending"
                backoff_secs = 2 ** min(attempts, 4) * 5
                stmt = update(Job).where(Job.id == job_id).values(
                    status=new_status,
                    error_message=err_msg[:500],
                    locked_by=None,
                    locked_at=None,
                    run_after=text(f"NOW() + INTERVAL '{backoff_secs} seconds'"),
                )
            else:
                stmt = update(Job).where(Job.id == job_id).values(
                    status="done",
                    completed_at=text("NOW()"),
                )
            await db.execute(stmt)
            await db.commit()

        return True

    async def _handle_download_asset(self, payload: dict):
        """Stream media from remote .np server with 64KB chunking and disk safety check."""
        import shutil

        # Disk Safety Governor: check free storage
        total, used, free = shutil.disk_usage(settings.DATA_DIR)
        if free < 5.0 * (1024 ** 3):  # Less than 5 GB
            raise Exception(f"Disk safety governor: low storage ({free / (1024 ** 3):.2f} GB free). Pausing media ingestion.")

        raw_asset_id = payload.get("raw_asset_id")
        url = payload["url"]
        asset_type = payload["asset_type"]
        tier = payload.get("tier", "other")

        target_dir = settings.RAW_PDFS_DIR if asset_type == "pdf" else settings.RAW_IMAGES_DIR
        ext = ".pdf" if asset_type == "pdf" else ".jpg"
        u_hash = dedup_service.compute_url_hash(url)
        dest_path = target_dir / f"{u_hash[:16]}{ext}"

        # Stream chunked I/O (never buffer entire PDF/image in memory)
        async with httpx.AsyncClient(verify=False, timeout=httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=10.0), follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code}")

                bytes_written = 0
                with open(dest_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
                        bytes_written += len(chunk)

                if asset_type == "image" and bytes_written < settings.MIN_IMAGE_SIZE_BYTES:
                    dest_path.unlink(missing_ok=True)
                    if raw_asset_id:
                        async with AsyncSessionLocal() as db:
                            await db.execute(update(RawAsset).where(RawAsset.id == raw_asset_id).values(status="skipped_small"))
                            await db.commit()
                    return

        file_hash = dedup_service.compute_file_hash(dest_path)
        file_size = dest_path.stat().st_size

        async with AsyncSessionLocal() as db:
            stmt = update(RawAsset).where(RawAsset.id == raw_asset_id).values(
                file_path=str(dest_path),
                file_hash=file_hash,
                file_size_bytes=file_size,
                status="downloaded",
            )
            await db.execute(stmt)

            next_job_type = "convert_pdf" if asset_type == "pdf" else "process_image"
            next_payload = {
                "raw_asset_id": raw_asset_id,
                "pdf_path" if asset_type == "pdf" else "image_path": str(dest_path),
                "tier": tier
            }

            # High-priority execution: process_image=1, convert_pdf=2 (never starved by downloads)
            next_priority = 2 if asset_type == "pdf" else 1

            db.add(Job(
                job_type=next_job_type,
                payload=next_payload,
                priority=next_priority,
                status="pending",
            ))
            await db.commit()

    async def _handle_convert_pdf(self, payload: dict):
        """Extract PDF pages using CPU worker subprocess."""
        raw_asset_id = payload["raw_asset_id"]
        pdf_path = payload["pdf_path"]
        tier = payload.get("tier", "gov")

        temp_dir = str(settings.RAW_IMAGES_DIR / f"pdf_extracted_{raw_asset_id}")

        loop = asyncio.get_running_loop()
        extracted = await loop.run_in_executor(
            self._cpu_executor,
            _convert_pdf_cpu_worker,
            pdf_path,
            temp_dir,
            15,  # Cap at first 15 pages for high-throughput bounded extraction
        )

        async with AsyncSessionLocal() as db:
            stmt = update(RawAsset).where(RawAsset.id == raw_asset_id).values(
                pdf_page_count=len(extracted),
                status="processed",
            )
            await db.execute(stmt)

            for item in extracted:
                db.add(Job(
                    job_type="process_image",
                    payload={
                        "raw_asset_id": raw_asset_id,
                        "image_path": item["temp_image_path"],
                        "pdf_page_number": item["page_number"],
                        "tier": tier,
                    },
                    priority=1,
                    status="pending",
                ))
            await db.commit()

        if not extracted:
            try:
                Path(temp_dir).rmdir()
            except OSError:
                pass

        if settings.DELETE_RAW_AFTER_PROCESSING:
            Path(pdf_path).unlink(missing_ok=True)

    async def _handle_process_image(self, payload: dict):
        """Resize to A4-max, WebP compress, and deduplicate using CPU subprocess."""
        raw_asset_id = payload.get("raw_asset_id")
        image_path = payload["image_path"]
        pdf_page_number = payload.get("pdf_page_number")
        tier = payload.get("tier", "other")

        out_dir = str(settings.PROCESSED_DIR / f"{tier}_np")

        loop = asyncio.get_running_loop()
        proc_meta = await loop.run_in_executor(
            self._cpu_executor,
            _process_image_cpu_worker,
            image_path,
            out_dir,
            tier,
        )

        if not proc_meta:
            Path(image_path).unlink(missing_ok=True)
            return

        async with AsyncSessionLocal() as db:
            is_dup, canon, sim = await dedup_service.check_duplicate(
                db=db,
                file_hash=proc_meta["file_hash"],
                perceptual_hash=proc_meta["perceptual_hash"],
            )

            if is_dup and canon:
                temp_dup = ImageModel(
                    raw_asset_id=raw_asset_id,
                    file_path=proc_meta["file_path"],
                    file_hash=proc_meta["file_hash"],
                    perceptual_hash=proc_meta["perceptual_hash"],
                    file_size_bytes=proc_meta["file_size_bytes"],
                    width=proc_meta["width"],
                    height=proc_meta["height"],
                    format=proc_meta["format"],
                    pdf_page_number=pdf_page_number,
                    status="duplicate",
                    is_approved=False,
                )
                db.add(temp_dup)
                await db.flush()
                await dedup_service.merge_duplicate(db, temp_dup, canon, sim or 1.0)
            else:
                new_image = ImageModel(
                    raw_asset_id=raw_asset_id,
                    file_path=proc_meta["file_path"],
                    file_hash=proc_meta["file_hash"],
                    perceptual_hash=proc_meta["perceptual_hash"],
                    file_size_bytes=proc_meta["file_size_bytes"],
                    width=proc_meta["width"],
                    height=proc_meta["height"],
                    format=proc_meta["format"],
                    pdf_page_number=pdf_page_number,
                    status="ready",
                    is_approved=False,
                )
                db.add(new_image)
                await db.commit()

        if settings.DELETE_RAW_AFTER_PROCESSING:
            p = Path(image_path)
            p.unlink(missing_ok=True)
            if p.parent.name.startswith("pdf_extracted_"):
                try:
                    p.parent.rmdir()
                except OSError:
                    pass  # directory not empty yet


queue_service = QueueService()
