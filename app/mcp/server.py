"""Model Context Protocol (MCP) Server for Open Nepali Image.

Designed for AI agents (OpenCode, Antigravity, Claude Code):
- Fetches images requiring OCR and captioning
- Saves AI annotations as 'ai_pending' requiring human review in the web UI
- Well-gated: AI cannot mark annotations as approved
- Suggests search terms and captions for category expansion
"""
import asyncio
from typing import Optional, List, Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from sqlalchemy import select, update
from .. import database as db_mod
from ..models import Image as ImageModel, SavedConcept
from ..services.dedup_service import dedup_service

# Initialize FastMCP Server
mcp = FastMCP("open-nepali-image")


@mcp.tool()
async def get_next_images_to_annotate(
    limit: Annotated[int, Field(ge=1, le=20, description="Number of images to fetch (max 20)")] = 5,
    prioritize_user_requested: Annotated[bool, Field(description="Prioritize documents that a human operator explicitly queued with 'Ask AI Assist'")] = True,
) -> list[dict]:
    """
    Fetch images that need annotation (OCR extraction or captioning).
    PRIORITY ORDER:
    1. Documents where the human operator clicked 'Ask AI Assist' in the web UI (ai_requested == True).
    2. Chronologically oldest unannotated documents in the platform queue.
    Returns image metadata, absolute file path, dimensions, and existing fields.
    """
    import os
    from ..models import RawAsset
    async with db_mod.AsyncSessionLocal() as db:
        stmt = (
            select(ImageModel, RawAsset.original_url)
            .outerjoin(RawAsset, ImageModel.raw_asset_id == RawAsset.id)
            .where(
                ImageModel.status.in_(["ready", "pending"]),
                ImageModel.is_approved == False,
                (ImageModel.annotation_source != "ai_pending") | (ImageModel.annotation_source.is_(None)),
            )
        )
        if prioritize_user_requested:
            stmt = stmt.order_by(
                ImageModel.ai_requested.desc(),
                ImageModel.ai_requested_at.asc().nullslast(),
                ImageModel.id.asc(),
            )
        else:
            stmt = stmt.order_by(ImageModel.id.asc())

        stmt = stmt.limit(limit)
        res = await db.execute(stmt)
        rows = res.all()

        results = []
        for img, raw_url in rows:
            results.append({
                "image_id": img.id,
                "file_path": img.file_path,
                "file_exists": os.path.exists(img.file_path) if img.file_path else False,
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "original_url": raw_url or "",
                "pdf_page_number": img.pdf_page_number,
                "has_text": img.has_text,
                "ai_requested": getattr(img, "ai_requested", False),
                "existing_ocr_text": img.ocr_text,
                "existing_caption_nepali": img.caption_nepali,
                "existing_caption_english": img.caption_english,
                "document_type": img.document_type or "",
                "tags": img.tags or [],
            })
        return results


@mcp.tool()
async def get_image_details(
    image_id: Annotated[int, Field(description="The unique ID of the image")],
) -> dict:
    """Fetch complete metadata and text content for a specific image ID."""
    import os
    from ..models import RawAsset
    async with db_mod.AsyncSessionLocal() as db:
        stmt = (
            select(ImageModel, RawAsset.original_url)
            .outerjoin(RawAsset, ImageModel.raw_asset_id == RawAsset.id)
            .where(ImageModel.id == image_id)
        )
        res = await db.execute(stmt)
        row = res.first()
        if not row:
            return {"error": f"Image ID {image_id} not found"}

        img, raw_url = row
        return {
            "image_id": img.id,
            "file_path": img.file_path,
            "file_exists": os.path.exists(img.file_path) if img.file_path else False,
            "width": img.width,
            "height": img.height,
            "format": img.format,
            "original_url": raw_url or "",
            "pdf_page_number": img.pdf_page_number,
            "has_text": img.has_text,
            "ocr_text": img.ocr_text or "",
            "caption_nepali": img.caption_nepali or "",
            "caption_english": img.caption_english or "",
            "annotation_text": img.annotation_text or "",
            "annotation_source": img.annotation_source or "none",
            "is_approved": img.is_approved,
            "document_type": img.document_type or "",
            "tags": img.tags or [],
        }


@mcp.tool()
async def submit_ai_annotation(
    image_id: Annotated[int, Field(description="Image ID to annotate")],
    caption_nepali: Annotated[str, Field(description="Accurate descriptive Nepali caption explaining visual content for CLIP/VLM")],
    caption_english: Annotated[Optional[str], Field(description="Accurate English translation or cross-lingual caption")] = None,
    ocr_text: Annotated[Optional[str], Field(description="Exact Nepali/Devanagari/English text extracted from the document or image")] = None,
    document_type: Annotated[Optional[str], Field(description="Document category: advertisement|banner|photo|notice|letter|gazette|form|certificate|receipt|card|other")] = None,
    tags: Annotated[Optional[List[str]], Field(description="Relevant categorical and descriptive tags")] = None,
    language_tags: Annotated[Optional[List[str]], Field(description="Languages detected in image (e.g. ['nepali', 'english'])")] = None,
    ai_output: Annotated[Optional[str], Field(description="Inspection reasoning, transcription, or multi-modal analysis text from AI model")] = None,
) -> dict:
    """
    Submit AI-generated OCR and captions for an image.
    GATED APPROVAL PROTOCOL:
    All annotations submitted via this tool are strictly marked as 'ai_pending' and is_approved=False.
    They are routed to the intermediate approval queue where the user will review, edit, or approve them.
    """
    if not caption_nepali or not caption_nepali.strip():
        return {"error": "caption_nepali cannot be empty", "success": False}

    async with db_mod.AsyncSessionLocal() as db:
        stmt = select(ImageModel).where(ImageModel.id == image_id)
        res = await db.execute(stmt)
        img = res.scalars().first()
        if not img:
            return {"error": f"Image ID {image_id} not found", "success": False}

        # Update metadata
        cleaned_ocr = ocr_text.strip() if ocr_text else None
        if cleaned_ocr:
            img.ocr_text = cleaned_ocr
            img.has_text = True
        else:
            img.ocr_text = None
            img.has_text = False

        img.caption_nepali = caption_nepali.strip()
        img.annotation_text = caption_nepali.strip()

        if caption_english is not None:
            img.caption_english = caption_english.strip()

        if document_type:
            img.document_type = document_type.strip().lower()

        if tags is not None:
            img.tags = tags

        if ai_output is not None:
            img.ai_output = ai_output.strip()

        if language_tags:
            img.language_tags = language_tags
        elif not img.language_tags:
            img.language_tags = ["nepali"]

        # STRICT GATING: Always ai_pending and requires human approval
        img.annotation_source = "ai_pending"
        img.annotated_by = "mcp_agent"
        img.is_approved = False
        img.ai_requested = False
        img.status = "ai_pending"

        await db.commit()

        return {
            "success": True,
            "image_id": image_id,
            "status": "ai_pending",
            "message": "Annotation successfully submitted to intermediate approval queue. User must approve in Web UI.",
        }


@mcp.tool()
async def suggest_search_and_caption_helper(
    nepali_concept: Annotated[str, Field(description="Nepali concept or keyword (e.g. 'नेपाल नागरिकता' or 'जग्गाधनी प्रमाणपूर्जा')")],
) -> dict:
    """
    Suggests high-quality Nepali caption and corresponding English search terms for acquiring more images.
    """
    from ..api.search import suggest_search_and_caption, SuggestionRequest
    resp = await suggest_search_and_caption(SuggestionRequest(concept_nepali=nepali_concept))
    return {
        "concept_nepali": resp.concept_nepali,
        "suggested_caption_nepali": resp.suggested_caption_nepali,
        "suggested_english_search_queries": resp.suggested_english_search_queries,
        "suggested_document_type": resp.suggested_document_type,
    }


@mcp.tool()
async def search_approved_dataset(
    query: Annotated[str, Field(description="Search term in Nepali or English")],
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> list[dict]:
    """Search images in the dataset that have already been human-approved."""
    async with db_mod.AsyncSessionLocal() as db:
        s_term = f"%{query}%"
        stmt = select(ImageModel).where(
            ImageModel.is_approved == True,
            (ImageModel.ocr_text.ilike(s_term)) |
            (ImageModel.caption_nepali.ilike(s_term)) |
            (ImageModel.caption_english.ilike(s_term)) |
            (ImageModel.annotation_text.ilike(s_term))
        ).limit(limit)

        res = await db.execute(stmt)
        images = res.scalars().all()
        return [
            {
                "id": img.id,
                "caption_nepali": img.caption_nepali,
                "caption_english": img.caption_english,
                "ocr_text": img.ocr_text,
                "document_type": img.document_type,
            }
            for img in images
        ]


@mcp.tool()
async def propose_and_save_concept(
    topic: Annotated[str, Field(description="Name or title of the Nepali document topic (e.g. 'विवाह दर्ता प्रमाण-पत्र')")],
    caption_nepali: Annotated[str, Field(description="High-accuracy Devanagari caption explaining document structure for VLM/CLIP")],
    search_query_en: Annotated[str, Field(description="High-converting English keywords for search engines (e.g. 'Nepal marriage certificate official format')")],
    document_type: Annotated[str, Field(description="Category: certificate|form|letter|gazette|deed|license|passport|receipt|other")] = "other",
    tags: Annotated[Optional[List[str]], Field(description="Metadata tags")] = None,
) -> dict:
    """
    Directly propose and save a new high-value concept into the persistent Concept Studio library.
    Allows AI agents to autonomously curate categories and prepare targeted ingestion pipelines.
    """
    async with db_mod.AsyncSessionLocal() as db:
        concept = SavedConcept(
            topic=topic.strip(),
            document_type=document_type.strip(),
            caption_nepali=caption_nepali.strip(),
            search_query_en=search_query_en.strip(),
            alternative_queries=[f"Nepal {topic} scanned", f"Government of Nepal {search_query_en}"],
            tags=tags or ["ai_curated"],
            is_downloaded=False,
            images_downloaded_count=0,
        )
        db.add(concept)
        await db.commit()
        await db.refresh(concept)

        return {
            "success": True,
            "concept_id": concept.id,
            "topic": concept.topic,
            "message": f"Successfully added concept #{concept.id} to the persistent library. Human can trigger 1-click ingestion in Concept Studio.",
        }


@mcp.prompt()
def nepali_vlm_annotator(image_id: Optional[int] = None) -> str:
    """System prompt providing standardized rules for Nepali Devanagari OCR and VLM ground-truth captioning."""
    target_str = f"Image #{image_id}" if image_id is not None else "the current image"
    return f"""You are an expert Devanagari OCR and Multimodal Vision-Language annotator for the Open Nepali Image platform.
Your task is to analyze {target_str} and provide high-quality ground-truth annotations:

1. Exact Devanagari OCR Text:
   - Transcribe all visible Nepali/Devanagari text preserving exact character order, Halanta (्), Chandrabindu (ँ), and Anusvara (ं).
   - If official seals, ministry names ('नेपाल सरकार', 'श्री ५ को सरकार'), or Bikram Sambat dates ('वि.सं. २०...') are present, transcribe them verbatim.
   - Do not translate OCR text to English; keep in original Devanagari script.

2. Nepali Ground-Truth Caption (for CLIP/VLM supervision):
   - Dense visual description: [दस्तावेजको किसिम] + [जारी गर्ने निकाय] + [मुख्य विषय] + [दृश्य विशेषताहरू].
   - Example: 'नेपाल सरकार जिल्ला प्रशासन कार्यालय काठमाडौँद्वारा जारी गरिएको नागरिकता प्रमाणपत्र, बायाँतर्फ छाप र आधिकारिक हस्ताक्षर।'

3. English Cross-Lingual Caption:
   - Accurate English description for cross-lingual vision-language alignment.

4. Document Category:
   - One of: advertisement | banner | photo | notice | letter | gazette | form | certificate | receipt | card | other.

Submit your results using the `submit_ai_annotation` tool. All annotations are securely routed to the human approval queue."""


if __name__ == "__main__":
    mcp.run()
