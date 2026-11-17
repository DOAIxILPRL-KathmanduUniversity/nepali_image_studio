"""API routes for targeted keyword image search and concept suggestion."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..schemas import ICrawlerSearch, ImageOut
from ..services.icrawler_service import icrawler_service

router = APIRouter(prefix="/api/search", tags=["search"])


class SuggestionRequest(BaseModel):
    concept_nepali: str


class SuggestionResponse(BaseModel):
    concept_nepali: str
    suggested_caption_nepali: str
    suggested_english_search_queries: List[str]
    suggested_document_type: str


@router.post("/icrawler", response_model=List[ImageOut])
async def search_and_download_icrawler(
    data: ICrawlerSearch,
    db: AsyncSession = Depends(get_db),
):
    """
    Search and download targeted images via iCrawler:
    Downloads, compresses to A4-max WebP, deduplicates, and saves for review.
    """
    new_images = await icrawler_service.ingest_keyword_images(
        db=db,
        query_nepali=data.query_nepali,
        query_english=data.query_english,
        max_images=data.max_images,
    )
    return new_images


@router.post("/suggest", response_model=SuggestionResponse)
async def suggest_search_and_caption(data: SuggestionRequest):
    """
    UI interface helper:
    Given a Nepali concept or theme (e.g. 'नेपाल नागरिकता' or 'जग्गाधनी प्रमाणपूर्जा'),
    suggests a structured Nepali caption and optimal English keywords for search engines.
    """
    c = data.concept_nepali.strip()

    # Domain vocabulary mapping for high-value Nepali administrative & cultural documents
    concept_map = {
        "नागरिकता": {
            "caption": "नेपाल सरकार द्वारा जारी गरिएको नेपाली नागरिकताको प्रमाणपत्र",
            "queries": ["Nepal citizenship certificate document", "Nepali nagarikta certificate format", "Nepal citizenship paper"],
            "doc_type": "certificate",
        },
        "जग्गाधनी": {
            "caption": "नेपाल सरकार भूमि व्यवस्था मन्त्रालय अन्तर्गतको जग्गाधनी प्रमाणपुर्जा (लालपुर्जा)",
            "queries": ["Nepal land ownership certificate lalpurja", "Lalpurja document Nepal", "Nepal malpot land deed"],
            "doc_type": "deed",
        },
        "लाइसेन्स": {
            "caption": "यातायात व्यवस्था विभागद्वारा जारी गरिएको सवारी चालक अनुमतिपत्र (स्मार्ट लाइसेन्स)",
            "queries": ["Nepal driving license smart card", "Nepal DOTM license format", "Nepal driving permit"],
            "doc_type": "card",
        },
        "राहदानी": {
            "caption": "नेपाल सरकार परराष्ट्र मन्त्रालयद्वारा जारी विद्युतीय राहदानी (ई-पासपोर्ट)",
            "queries": ["Nepal passport e-passport bio-page", "Nepal passport sample document"],
            "doc_type": "passport",
        },
        "राजपत्र": {
            "caption": "मुद्रण विभागद्वारा प्रकाशित नेपाल राजपत्रको आधिकारिक सूचना पृष्ठ",
            "queries": ["Nepal gazette rajpatra official document", "Nepal rajpatra scanned page", "Nepal law gazette"],
            "doc_type": "gazette",
        },
        "प्रमाणपत्र": {
            "caption": "नेपालका आधिकारिक निकाय वा शैक्षिक संस्थाबाट जारी गरिएको प्रमाणपत्र",
            "queries": ["Nepal official certificate format", "Nepal board certificate transcript"],
            "doc_type": "certificate",
        },
    }

    # Find matching keyword
    matched = None
    for k, v in concept_map.items():
        if k in c:
            matched = v
            break

    if matched:
        return SuggestionResponse(
            concept_nepali=c,
            suggested_caption_nepali=matched["caption"],
            suggested_english_search_queries=matched["queries"],
            suggested_document_type=matched["doc_type"],
        )

    # General fallback
    return SuggestionResponse(
        concept_nepali=c,
        suggested_caption_nepali=f"नेपाल सम्बन्धी आधिकारिक दस्तावेज वा तस्विर: {c}",
        suggested_english_search_queries=[f"Nepal {c} document", f"Nepal {c} official notice", f"{c} Nepal archive"],
        suggested_document_type="document",
    )
