"""Automated test suite for Open Nepali Image platform."""
import asyncio
import os
import uuid
import pytest
from pathlib import Path
from PIL import Image
from app.config import settings
from app import database as app_db
from app.database import init_db
from app.models import Image as ImageModel, Source, Job, CrawledDomain
from app.services.dedup_service import dedup_service
from app.services.image_service import image_service
from app.services.pdf_service import pdf_service
from app.services.cleanup_service import cleanup_service
from app.services.domain_harvester import domain_harvester
from app.services.crawler_service import is_allowed_np_domain, get_domain_tier, crawler_service
from app.api.images import generate_document_svg_placeholder


@pytest.mark.asyncio
async def test_database_and_schema():
    """Verify PostgreSQL tables are properly created and queryable in test database."""
    await init_db()
    async with app_db.AsyncSessionLocal() as db:
        unique_url = f"https://moha.gov.np/test_{uuid.uuid4().hex[:8]}"
        source = Source(
            url=unique_url,
            url_hash=dedup_service.compute_url_hash(unique_url),
            domain="moha.gov.np",
            domain_tier="gov",
            source_type="crawl",
            status="pending",
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)
        assert source.id is not None
        assert source.domain_tier == "gov"


@pytest.mark.asyncio
async def test_domain_filtering_and_harvesting():
    """Verify strict .np domain filtering and domain harvester regex."""
    assert is_allowed_np_domain("https://moha.gov.np/citizen-form") is True
    assert is_allowed_np_domain("https://tu.edu.np/library") is True
    assert is_allowed_np_domain("https://nrb.org.np/circulars") is True
    assert is_allowed_np_domain("https://kathmandu.gov.np/notices") is True

    # MUST REJECT foreign and .com domains
    assert is_allowed_np_domain("https://google.com/search") is False
    assert is_allowed_np_domain("https://ekantipur.com/news") is False
    assert is_allowed_np_domain("https://facebook.com/groups") is False

    # Harvest from arbitrary HTML content
    sample_html = """
    <div>
        <a href="https://nepalpolice.gov.np/notices">Police Notices</a>
        <a href="http://elibrary.tucl.edu.np/handle/123">TU Library</a>
        <p>Visit us at www.dop.gov.np or email info@ku.edu.np</p>
        <p>External link: https://somewebsite.com/test</p>
    </div>
    """
    harvested = domain_harvester.extract_domains_from_text(sample_html)
    assert any("nepalpolice.gov.np" in d for d in harvested)
    assert any("elibrary.tucl.edu.np" in d for d in harvested)
    assert any("dop.gov.np" in d for d in harvested)
    assert any("ku.edu.np" in d for d in harvested)
    # Never harvest non-np
    assert not any("somewebsite.com" in d for d in harvested)


@pytest.mark.asyncio
async def test_svg_placeholder_generation():
    """Verify SVG placeholder generation produces valid SVG content for missing images."""
    svg = generate_document_svg_placeholder(42, "citizenship", "Ready")
    assert "<svg" in svg
    assert "</svg>" in svg
    assert "Document #42" in svg
    assert "CITIZENSHIP" in svg


@pytest.mark.asyncio
async def test_image_processing_and_a4_constraint():
    """Verify image is converted to WebP, RGB, and constrained to A4-max (2480px)."""
    test_dir = settings.DATA_DIR / "test_scratch"
    test_dir.mkdir(parents=True, exist_ok=True)
    raw_img_path = test_dir / f"large_doc_{uuid.uuid4().hex[:6]}.png"

    img = Image.new("RGBA", (3000, 4000), color=(240, 240, 240, 255))
    img.save(raw_img_path, "PNG")

    meta = image_service.process_and_compress(
        input_path=raw_img_path,
        output_dir=test_dir,
        filename_prefix="test",
    )

    assert meta is not None
    assert meta["format"] == "webp"
    # Max dimension must not exceed 2480px (A4 max)
    assert max(meta["width"], meta["height"]) <= settings.MAX_IMAGE_DIMENSION
    assert Path(meta["file_path"]).exists()

    # Cleanup test files
    raw_img_path.unlink(missing_ok=True)
    Path(meta["file_path"]).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_deduplication_and_merge():
    """Verify 3-layer deduplication catches duplicate and merges annotations."""
    test_dir = settings.DATA_DIR / "test_scratch"
    test_dir.mkdir(parents=True, exist_ok=True)

    uid = uuid.uuid4().hex[:8]
    img_path = test_dir / f"canon_{uid}.webp"
    img = Image.new("RGB", (300, 400), color=(hash(uid) % 250, (hash(uid) >> 4) % 250, (hash(uid) >> 8) % 250))
    img.save(img_path, "WEBP")

    f_hash = dedup_service.compute_file_hash(img_path)
    p_hash = dedup_service.compute_perceptual_hash(img_path)

    async with app_db.AsyncSessionLocal() as db:
        # Insert canonical image
        canon = ImageModel(
            file_path=str(img_path),
            file_hash=f_hash,
            perceptual_hash=p_hash,
            width=300,
            height=400,
            format="webp",
            status="ready",
        )
        db.add(canon)
        await db.commit()
        await db.refresh(canon)

        # Check duplicate using file_hash
        is_dup, matched_canon, sim = await dedup_service.check_duplicate(
            db, file_hash=f_hash, perceptual_hash=p_hash
        )
        assert is_dup is True
        assert matched_canon.id == canon.id

        # Test merge: duplicate has an annotation
        dup = ImageModel(
            file_path=str(img_path),
            file_hash=f"{f_hash[:30]}_dup_{uid}",
            perceptual_hash=p_hash,
            width=300,
            height=400,
            format="webp",
            caption_nepali="नेपाल नागरिकताको आधिकारिक प्रतिलिपि",
            annotation_text="नेपाल नागरिकताको आधिकारिक प्रतिलिपि",
            status="ready",
        )
        db.add(dup)
        await db.commit()
        await db.refresh(dup)

        await dedup_service.merge_duplicate(db, dup, canon, sim or 1.0)

        # Canon must have received the annotation
        await db.refresh(canon)
        assert canon.caption_nepali == "नेपाल नागरिकताको आधिकारिक प्रतिलिपि"
        assert dup.status == "duplicate"

    img_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_mcp_gated_approval_logic():
    """Verify MCP AI annotations are strictly marked 'ai_pending' and require review."""
    from app.mcp.server import submit_ai_annotation

    uid = uuid.uuid4().hex[:8]
    async with app_db.AsyncSessionLocal() as db:
        test_img = ImageModel(
            file_path=f"/tmp/test_mcp_{uid}.webp",
            file_hash=f"test_mcp_hash_{uid}",
            width=800,
            height=600,
            status="ready",
            is_approved=False,
        )
        db.add(test_img)
        await db.commit()
        await db.refresh(test_img)

        # Call MCP tool
        result = await submit_ai_annotation(
            image_id=test_img.id,
            ocr_text="श्री ५ को सरकार, गृह मन्त्रालय",
            caption_nepali="नेपाल सरकारको आधिकारिक सूचना पत्र",
            caption_english="Government of Nepal official circular",
            document_type="letter",
        )

        assert result["success"] is True
        assert result["status"] == "ai_pending"

        await db.refresh(test_img)
        # GATING CHECK: must NOT be approved automatically
        assert test_img.is_approved is False
        assert test_img.annotation_source == "ai_pending"
        assert test_img.annotated_by == "mcp_agent"
        assert test_img.ocr_text == "श्री ५ को सरकार, गृह मन्त्रालय"
