"""API routes for AI Concept Studio and Saved Concept Library."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models import SavedConcept, Image as ImageModel
from ..schemas import (
    SavedConceptCreate, SavedConceptOut,
    AiConceptSuggestRequest, AiConceptSuggestResponse,
    ImageOut
)
from ..services.concept_ai_service import concept_ai_service
from ..services.icrawler_service import icrawler_service

router = APIRouter(prefix="/api/concepts", tags=["concepts"])


@router.post("/ai-suggest", response_model=AiConceptSuggestResponse)
async def ai_suggest_concept(payload: Optional[AiConceptSuggestRequest] = None):
    """
    AI Concept Assistant:
    Given an optional user prompt or keyword, suggests a structured Devanagari caption,
    target document type, and high-converting English keywords for search engines.
    """
    topic = payload.topic if payload else None
    res = concept_ai_service.suggest_concept(topic)
    return AiConceptSuggestResponse(**res)


@router.post("/ai-batch", response_model=List[AiConceptSuggestResponse])
async def ai_batch_concepts(count: int = Query(5, ge=1, le=10)):
    """Generate a batch of diverse, high-value Nepali document concepts."""
    res_list = concept_ai_service.generate_batch_concepts(count)
    return [AiConceptSuggestResponse(**r) for r in res_list]


@router.get("", response_model=List[SavedConceptOut])
async def list_saved_concepts(
    is_downloaded: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List saved concepts in the library with optional status and search filter."""
    stmt = select(SavedConcept).order_by(SavedConcept.created_at.desc())

    if is_downloaded is not None:
        stmt = stmt.where(SavedConcept.is_downloaded == is_downloaded)

    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            (SavedConcept.topic.ilike(term)) |
            (SavedConcept.caption_nepali.ilike(term)) |
            (SavedConcept.search_query_en.ilike(term))
        )

    res = await db.execute(stmt.limit(limit))
    return res.scalars().all()


@router.post("", response_model=SavedConceptOut, status_code=status.HTTP_201_CREATED)
async def save_concept(data: SavedConceptCreate, db: AsyncSession = Depends(get_db)):
    """Save an AI-suggested or curated concept to the persistent concept library."""
    concept = SavedConcept(
        topic=data.topic.strip(),
        document_type=data.document_type.strip(),
        caption_nepali=data.caption_nepali.strip(),
        search_query_en=data.search_query_en.strip(),
        alternative_queries=data.alternative_queries or [],
        tags=data.tags or [],
        is_downloaded=False,
        images_downloaded_count=0,
    )
    db.add(concept)
    await db.commit()
    await db.refresh(concept)
    return concept


@router.delete("/{concept_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_concept(concept_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a concept from the library."""
    stmt = select(SavedConcept).where(SavedConcept.id == concept_id)
    res = await db.execute(stmt)
    concept = res.scalars().first()
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")

    await db.delete(concept)
    await db.commit()
    return None


@router.post("/{concept_id}/run", response_model=List[ImageOut])
async def run_concept_ingestion(
    concept_id: int,
    max_images: int = Query(15, ge=5, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute targeted iCrawler ingestion for a saved concept:
    1. Downloads up to max_images using the concept's optimal English keywords
    2. Converts to A4-max WebP and deduplicates
    3. Automatically pre-populates images with the concept's Devanagari caption and category
    4. Updates the concept's downloaded count and status
    """
    stmt = select(SavedConcept).where(SavedConcept.id == concept_id)
    res = await db.execute(stmt)
    concept = res.scalars().first()
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")

    new_images = await icrawler_service.ingest_keyword_images(
        db=db,
        query_nepali=concept.topic,
        query_english=concept.search_query_en,
        max_images=max_images,
    )

    # Attach concept's Devanagari caption and document category to newly ingested images
    for img in new_images:
        img_stmt = select(ImageModel).where(ImageModel.id == img.id)
        img_res = await db.execute(img_stmt)
        live_img = img_res.scalars().first()
        if live_img:
            if not live_img.caption_nepali:
                live_img.caption_nepali = concept.caption_nepali
            if not live_img.document_type:
                live_img.document_type = concept.document_type
            if concept.tags:
                existing_tags = set(live_img.tags or [])
                existing_tags.update(concept.tags)
                live_img.tags = list(existing_tags)

    concept.is_downloaded = True
    concept.images_downloaded_count = (concept.images_downloaded_count or 0) + len(new_images)
    await db.commit()

    return new_images
