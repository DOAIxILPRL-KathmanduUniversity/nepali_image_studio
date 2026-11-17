"""Deduplication Service: URL hash, File content hash, and Perceptual hash (pHash)."""
import hashlib
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image
import imagehash
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Image as ImageModel, DuplicateGroup, DuplicateMember


class DedupService:
    """Three-layer deduplication for images and documents."""

    @staticmethod
    def normalize_url(url: str) -> str:
        """
        Normalize URL for consistent hashing and single-crawl guarantee.
        - Strips fragments (#section)
        - Lowercases scheme and host
        - Removes tracking query params (utm_*, ref, etc.)
        - Normalizes trailing slashes on empty paths
        """
        try:
            from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
            parsed = urlparse(url.strip())
            scheme = parsed.scheme.lower() or "https"
            netloc = parsed.netloc.lower()
            # Strip standard ports
            if netloc.endswith(":80") and scheme == "http":
                netloc = netloc[:-3]
            elif netloc.endswith(":443") and scheme == "https":
                netloc = netloc[:-4]

            path = parsed.path or "/"
            if path != "/" and path.endswith("/"):
                path = path[:-1]

            # Filter out tracking query params and sort
            tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid"}
            query_items = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in tracking_params]
            query_items.sort()
            clean_query = urlencode(query_items)

            return urlunparse((scheme, netloc, path, "", clean_query, ""))
        except Exception:
            u = url.strip().split("#")[0]
            if u.endswith("/"):
                u = u[:-1]
            return u.lower()

    @classmethod
    def compute_url_hash(cls, url: str) -> str:
        """SHA-256 of normalized URL."""
        return hashlib.sha256(cls.normalize_url(url).encode("utf-8")).hexdigest()

    @staticmethod
    def compute_file_hash(file_path: str | Path) -> str:
        """SHA-256 of file bytes."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def compute_perceptual_hash(file_path: str | Path) -> Optional[str]:
        """Compute 64-bit pHash string from image file."""
        try:
            with Image.open(file_path) as img:
                return str(imagehash.phash(img))
        except Exception:
            return None

    @staticmethod
    def phash_distance(hash1_str: str, hash2_str: str) -> int:
        """Calculate Hamming distance between two pHash strings via CPU bit_count POPCNT."""
        try:
            return (int(hash1_str, 16) ^ int(hash2_str, 16)).bit_count()
        except Exception:
            try:
                h1 = imagehash.hex_to_hash(hash1_str)
                h2 = imagehash.hex_to_hash(hash2_str)
                return h1 - h2
            except Exception:
                return 999

    async def check_duplicate(
        self,
        db: AsyncSession,
        file_hash: str,
        perceptual_hash: Optional[str] = None,
        phash_threshold: int = 6,
        exclude_id: Optional[int] = None,
    ) -> Tuple[bool, Optional[ImageModel], Optional[float]]:
        """
        Check if an image is a duplicate based on file_hash or perceptual_hash.
        Returns (is_duplicate, canonical_image, similarity_score).
        """
        # 1. Exact file content hash match (100% duplicate)
        stmt = select(ImageModel).where(
            ImageModel.file_hash == file_hash,
            ImageModel.status != "skipped",
            ImageModel.status != "duplicate",
        )
        if exclude_id is not None:
            stmt = stmt.where(ImageModel.id != exclude_id)

        res = await db.execute(stmt)
        exact_match = res.scalars().first()
        if exact_match:
            return True, exact_match, 1.0

        # 2. Perceptual hash distance match
        if perceptual_hash:
            stmt = select(ImageModel).where(
                ImageModel.perceptual_hash.isnot(None),
                ImageModel.status != "skipped",
                ImageModel.status != "duplicate",
            )
            if exclude_id is not None:
                stmt = stmt.where(ImageModel.id != exclude_id)
            stmt = stmt.order_by(ImageModel.id.desc()).limit(2000)

            res = await db.execute(stmt)
            candidates = res.scalars().all()

            best_match = None
            min_dist = 999

            try:
                h1_int = int(perceptual_hash, 16)
            except Exception:
                h1_int = None

            for cand in candidates:
                if cand.perceptual_hash:
                    if h1_int is not None:
                        try:
                            dist = (h1_int ^ int(cand.perceptual_hash, 16)).bit_count()
                        except Exception:
                            dist = self.phash_distance(perceptual_hash, cand.perceptual_hash)
                    else:
                        dist = self.phash_distance(perceptual_hash, cand.perceptual_hash)

                    if dist <= phash_threshold and dist < min_dist:
                        min_dist = dist
                        best_match = cand

            if best_match:
                similarity = (64 - min_dist) / 64.0
                return True, best_match, similarity

        return False, None, 0.0

    async def merge_duplicate(
        self,
        db: AsyncSession,
        duplicate_image: ImageModel,
        canonical_image: ImageModel,
        similarity_score: float,
    ) -> ImageModel:
        """
        Merge duplicate into canonical:
        - If duplicate has manual or approved annotation and canonical doesn't, copy to canonical
        - If duplicate has OCR text / caption and canonical doesn't, copy to canonical
        - Mark duplicate status='duplicate' and delete duplicate image file
        - Record duplicate group membership
        """
        if duplicate_image.annotation_text and not canonical_image.annotation_text:
            canonical_image.annotation_text = duplicate_image.annotation_text
            canonical_image.annotation_source = duplicate_image.annotation_source
            canonical_image.annotated_by = duplicate_image.annotated_by
            canonical_image.annotated_at = duplicate_image.annotated_at
            canonical_image.is_approved = duplicate_image.is_approved

        if duplicate_image.ocr_text and not canonical_image.ocr_text:
            canonical_image.ocr_text = duplicate_image.ocr_text
            canonical_image.has_text = duplicate_image.has_text

        if duplicate_image.caption_nepali and not canonical_image.caption_nepali:
            canonical_image.caption_nepali = duplicate_image.caption_nepali
        if duplicate_image.caption_english and not canonical_image.caption_english:
            canonical_image.caption_english = duplicate_image.caption_english

        if duplicate_image.document_type and not canonical_image.document_type:
            canonical_image.document_type = duplicate_image.document_type

        stmt = select(DuplicateGroup).where(DuplicateGroup.canonical_image_id == canonical_image.id)
        res = await db.execute(stmt)
        group = res.scalars().first()

        if not group:
            group = DuplicateGroup(canonical_image_id=canonical_image.id, member_count=1)
            db.add(group)
            await db.flush()
            m_canon = DuplicateMember(
                group_id=group.id,
                image_id=canonical_image.id,
                similarity_score=1.0,
                is_canonical=True,
            )
            db.add(m_canon)

        group.member_count += 1
        m_dup = DuplicateMember(
            group_id=group.id,
            image_id=duplicate_image.id,
            similarity_score=similarity_score,
            is_canonical=False,
        )
        db.add(m_dup)

        duplicate_image.status = "duplicate"

        try:
            p = Path(duplicate_image.file_path)
            if p.exists() and p != Path(canonical_image.file_path):
                p.unlink(missing_ok=True)
        except Exception:
            pass

        await db.commit()
        return canonical_image


dedup_service = DedupService()
