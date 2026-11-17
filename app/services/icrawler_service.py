"""iCrawler service for targeted keyword-based image acquisition with deduplication."""
import asyncio
import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from icrawler.builtin import BingImageCrawler, GoogleImageCrawler
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import Source, RawAsset, Image as ImageModel
from .image_service import image_service
from .dedup_service import dedup_service


class ICrawlerService:
    """Acquires targeted images by keyword for low-resource Nepali categories."""

    @staticmethod
    def search_and_download(
        keyword: str,
        output_dir: str | Path,
        max_num: int = 20,
        crawler_type: str = "google",
    ) -> List[str]:
        """Run icrawler to fetch images for keyword into output_dir."""
        out_p = Path(output_dir)
        out_p.mkdir(parents=True, exist_ok=True)

        crawler_cls = GoogleImageCrawler if crawler_type == "google" else BingImageCrawler
        crawler = crawler_cls(storage={"root_dir": str(out_p)})
        try:
            crawler.crawl(keyword=keyword, max_num=max_num, overwrite=False)
        except Exception:
            # Fallback to Bing if Google encounters rate limits or errors
            if crawler_type == "google":
                try:
                    fallback_crawler = BingImageCrawler(storage={"root_dir": str(out_p)})
                    fallback_crawler.crawl(keyword=keyword, max_num=max_num, overwrite=False)
                except Exception:
                    pass

        # Return list of downloaded file paths
        results = []
        for f in out_p.iterdir():
            if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
                results.append(str(f))
        return results

    async def ingest_keyword_images(
        self,
        db: AsyncSession,
        query_nepali: str,
        query_english: Optional[str] = None,
        max_images: int = 20,
        suggested_caption: Optional[str] = None,
    ) -> List[ImageModel]:
        """
        Download keyword images, compress to A4-max WebP, deduplicate, and save.
        """
        search_query = query_english if query_english else query_nepali
        temp_dir = settings.RAW_IMAGES_DIR / f"icrawler_{abs(hash(search_query)) % 100000}"
        
        # 1. Download asynchronously in thread executor
        loop = asyncio.get_running_loop()
        downloaded_paths = await loop.run_in_executor(
            None,
            self.search_and_download,
            search_query,
            temp_dir,
            max_images,
            "google",
        )

        # 2. Register source
        source_url = f"icrawler://search?q={search_query}"
        source = Source(
            url=source_url,
            url_hash=dedup_service.compute_url_hash(source_url),
            domain="search.engine",
            domain_tier="icrawler",
            source_type="icrawler",
            status="done",
        )
        db.add(source)
        await db.flush()

        saved_images = []
        processed_dir = settings.PROCESSED_DIR / "icrawler"

        # 3. Process each downloaded image
        for raw_path in downloaded_paths:
            proc_meta = image_service.process_and_compress(
                input_path=raw_path,
                output_dir=processed_dir,
                filename_prefix="icrawler",
            )
            if not proc_meta:
                # Discard file if invalid or too small
                Path(raw_path).unlink(missing_ok=True)
                continue

            # 4. Check for duplicates
            is_dup, canon, sim = await dedup_service.check_duplicate(
                db=db,
                file_hash=proc_meta["file_hash"],
                perceptual_hash=proc_meta["perceptual_hash"],
            )

            if is_dup and canon:
                # If duplicate already exists, remove current file
                Path(proc_meta["file_path"]).unlink(missing_ok=True)
                continue

            # 5. Insert new image
            img_item = ImageModel(
                source_id=source.id,
                file_path=proc_meta["file_path"],
                file_hash=proc_meta["file_hash"],
                perceptual_hash=proc_meta["perceptual_hash"],
                file_size_bytes=proc_meta["file_size_bytes"],
                width=proc_meta["width"],
                height=proc_meta["height"],
                format=proc_meta["format"],
                caption_nepali=suggested_caption or query_nepali,
                caption_english=query_english,
                tags=[query_nepali] + ([query_english] if query_english else []),
                status="ready",  # ready for review / annotation
            )
            db.add(img_item)
            saved_images.append(img_item)

            # Cleanup raw download file immediately
            Path(raw_path).unlink(missing_ok=True)

        await db.commit()

        # Clean up temp folder
        shutil.rmtree(temp_dir, ignore_errors=True)

        return saved_images


icrawler_service = ICrawlerService()
