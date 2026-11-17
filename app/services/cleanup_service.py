"""Disk space and memory cleanup service for 8GB Mac environment."""
import shutil
from pathlib import Path
from typing import Dict, Any
from sqlalchemy import select, delete, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Image as ImageModel, RawAsset
from ..config import settings


class CleanupService:
    """Aggressively reclaims disk space so local storage never exceeds quota."""

    @staticmethod
    def get_disk_stats() -> Dict[str, Any]:
        """Check total, used, and free disk space in GB."""
        usage = shutil.disk_usage(settings.DATA_DIR)
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        return {
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "warning": free_gb < 5.0,
        }

    async def cleanup_skipped_files(self, db: AsyncSession) -> int:
        """Permanently delete files marked as 'skipped' by user or system."""
        stmt = select(ImageModel).where(ImageModel.status == "skipped")
        res = await db.execute(stmt)
        skipped_images = res.scalars().all()

        deleted_count = 0
        for img in skipped_images:
            if img.file_path:
                try:
                    p = Path(img.file_path)
                    if p.exists():
                        p.unlink(missing_ok=True)
                        deleted_count += 1
                except Exception:
                    pass

        # Also purge from DB to keep table clean
        del_stmt = delete(ImageModel).where(ImageModel.status == "skipped")
        await db.execute(del_stmt)
        await db.commit()
        return deleted_count

    async def cleanup_raw_assets(self, db: AsyncSession) -> int:
        """
        Delete original raw files once they are processed into final WebP images.
        Preserves metadata in database while setting file_path to null.
        """
        stmt = select(RawAsset).where(
            RawAsset.status == "processed",
            RawAsset.file_path.isnot(None)
        ).limit(500)
        res = await db.execute(stmt)
        raw_items = res.scalars().all()

        cleaned_count = 0
        for item in raw_items:
            if item.file_path:
                try:
                    p = Path(item.file_path)
                    if p.exists():
                        p.unlink(missing_ok=True)
                        cleaned_count += 1
                    item.file_path = None
                except Exception:
                    pass

        await db.commit()
        return cleaned_count

    async def cleanup_duplicate_files(self, db: AsyncSession) -> int:
        """Remove physical files for images marked as duplicate."""
        stmt = select(ImageModel).where(
            ImageModel.status == "duplicate",
            ImageModel.file_path.isnot(None)
        ).limit(500)
        res = await db.execute(stmt)
        duplicates = res.scalars().all()

        removed_count = 0
        for dup in duplicates:
            if dup.file_path:
                try:
                    p = Path(dup.file_path)
                    if p.exists():
                        p.unlink(missing_ok=True)
                        removed_count += 1
                except Exception:
                    pass

        await db.commit()
        return removed_count

    async def vacuum_database(self, db: AsyncSession):
        """Run database VACUUM ANALYZE to reclaim disk space from deleted rows."""
        try:
            # PostgreSQL requires autocommit for VACUUM
            await db.execute(text("COMMIT"))
            await db.execute(text("VACUUM ANALYZE"))
        except Exception:
            pass


cleanup_service = CleanupService()
