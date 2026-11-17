"""API routes for image management, pagination, human annotation, and SVG fallback."""
import math
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from fastapi.responses import FileResponse
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models import Image as ImageModel
from ..schemas import ImageOut, ImageAnnotation, ImageSkip
from ..services.cleanup_service import cleanup_service

router = APIRouter(prefix="/api/images", tags=["images"])


def generate_document_svg_placeholder(image_id: int, doc_type: str = "document", status_text: str = "Ready") -> str:
    """Generate crisp, high-contrast SVG placeholder for missing or in-transit documents."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400" viewBox="0 0 600 400" fill="#0f172a">
  <rect width="600" height="400" fill="#0f172a" rx="12"/>
  <rect x="200" y="55" width="200" height="270" rx="8" fill="#1e293b" stroke="#334155" stroke-width="2"/>
  <circle cx="300" cy="125" r="30" fill="#334155"/>
  <path d="M 288 125 L 297 134 L 312 118" stroke="#10b981" stroke-width="3.5" fill="none" stroke-linecap="round"/>
  <rect x="230" y="175" width="140" height="10" rx="4" fill="#475569"/>
  <rect x="230" y="196" width="110" height="8" rx="4" fill="#334155"/>
  <rect x="230" y="212" width="125" height="8" rx="4" fill="#334155"/>
  <rect x="230" y="228" width="90" height="8" rx="4" fill="#334155"/>
  <text x="300" y="280" text-anchor="middle" fill="#94a3b8" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="14" font-weight="600">Document #{image_id}</text>
  <text x="300" y="302" text-anchor="middle" fill="#64748b" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="12">{doc_type.upper()} • {status_text.upper()}</text>
</svg>"""


class AiAssistRequest(BaseModel):
    prompt: Optional[str] = None


class BatchImageActionRequest(BaseModel):
    action: str  # approve | set_category | discard
    image_ids: List[int]
    category: Optional[str] = None


@router.get("")
async def list_images(
    status_filter: Optional[str] = Query(None, alias="status"),
    is_approved: Optional[bool] = Query(None),
    has_annotation: Optional[bool] = Query(None),
    annotation_source: Optional[str] = Query(None),
    document_type: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),  # unannotated | ai_requested | ai_pending | approved | skipped
    search: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("newest"),
    page: int = Query(1, ge=1),
    limit: int = Query(24, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Page-by-page paginated image list with metadata & sorting:
    Returns {items: [...], total, page, per_page, total_pages, stage_counts}.
    """
    base_where = [ImageModel.status != "duplicate"]

    # Explicit stage filtering for clear separation
    if stage == "unannotated":
        base_where.extend([
            ImageModel.status != "skipped",
            ImageModel.is_approved == False,
            (ImageModel.annotation_source != "ai_pending") | (ImageModel.annotation_source.is_(None)),
        ])
    elif stage == "ai_requested":
        base_where.extend([
            ImageModel.ai_requested == True,
            ImageModel.is_approved == False,
        ])
    elif stage == "ai_pending":
        base_where.extend([
            ImageModel.annotation_source == "ai_pending",
            ImageModel.is_approved == False,
        ])
    elif stage == "approved":
        base_where.append(ImageModel.is_approved == True)
    elif stage == "skipped":
        base_where.append(ImageModel.status == "skipped")
    else:
        # Standard query filters
        if status_filter:
            base_where.append(ImageModel.status == status_filter)
        if is_approved is not None:
            base_where.append(ImageModel.is_approved == is_approved)
        if annotation_source:
            base_where.append(ImageModel.annotation_source == annotation_source)

    if document_type:
        base_where.append(ImageModel.document_type == document_type)
    if has_annotation is True:
        base_where.append(ImageModel.annotation_text.isnot(None))
    elif has_annotation is False:
        base_where.append(ImageModel.annotation_text.is_(None))

    if search:
        s_term = f"%{search}%"
        base_where.append(
            (ImageModel.ocr_text.ilike(s_term)) |
            (ImageModel.caption_nepali.ilike(s_term)) |
            (ImageModel.caption_english.ilike(s_term)) |
            (ImageModel.annotation_text.ilike(s_term)) |
            (ImageModel.document_type.ilike(s_term))
        )

    # Count total
    count_stmt = select(func.count(ImageModel.id)).where(*base_where)
    total = (await db.execute(count_stmt)).scalar_one()

    # Dynamic sorting
    if sort_by == "oldest":
        order_clause = ImageModel.id.asc()
    elif sort_by == "file_size":
        order_clause = ImageModel.file_size_bytes.desc().nullslast()
    elif sort_by == "resolution":
        order_clause = (ImageModel.width * ImageModel.height).desc()
    elif sort_by == "random":
        order_clause = func.random()
    else:  # newest
        order_clause = ImageModel.id.desc()

    # Fetch page
    stmt = select(ImageModel).where(*base_where).order_by(
        order_clause
    ).offset((page - 1) * limit).limit(limit)

    res = await db.execute(stmt)
    items = res.scalars().all()

    total_pages = max(1, math.ceil(total / limit))

    return {
        "items": [ImageOut.model_validate(it) for it in items],
        "total": total,
        "page": page,
        "per_page": limit,
        "total_pages": total_pages,
        "sort_by": sort_by,
        "stage": stage,
    }


@router.get("/next-unannotated")
async def get_next_unannotated_document(
    current_id: Optional[int] = Query(None),
    stage: str = Query("unannotated"),
    direction: str = Query("next"),
    db: AsyncSession = Depends(get_db),
):
    """Fetch the next/prev unannotated document for the annotator workspace."""
    base_where = [ImageModel.status != "duplicate"]
    if stage == "unannotated":
        base_where.extend([
            ImageModel.status != "skipped",
            ImageModel.is_approved == False,
            (ImageModel.annotation_source != "ai_pending") | (ImageModel.annotation_source.is_(None)),
        ])
    elif stage == "ai_requested":
        base_where.extend([
            ImageModel.ai_requested == True,
            ImageModel.is_approved == False,
        ])
    elif stage == "ai_pending":
        base_where.extend([
            ImageModel.annotation_source == "ai_pending",
            ImageModel.is_approved == False,
        ])
    elif stage == "approved":
        base_where.append(ImageModel.is_approved == True)

    if current_id:
        if direction == "prev":
            stmt = select(ImageModel).where(*base_where, ImageModel.id < current_id).order_by(ImageModel.id.desc()).limit(1)
        else:
            stmt = select(ImageModel).where(*base_where, ImageModel.id > current_id).order_by(ImageModel.id.asc()).limit(1)
    else:
        stmt = select(ImageModel).where(*base_where).order_by(ImageModel.id.asc()).limit(1)

    res = await db.execute(stmt)
    img = res.scalars().first()
    if not img and current_id:
        # Wrap around or pick first
        fallback_stmt = select(ImageModel).where(*base_where).order_by(ImageModel.id.asc()).limit(1)
        img = (await db.execute(fallback_stmt)).scalars().first()

    if not img:
        return {"item": None, "message": "No documents available in this stage"}

    return {"item": ImageOut.model_validate(img)}


@router.get("/categories")
async def list_document_categories(db: AsyncSession = Depends(get_db)):
    """Return all distinct document categories present in the database plus standard defaults."""
    stmt = select(ImageModel.document_type).where(
        ImageModel.document_type.isnot(None),
        ImageModel.document_type != "",
    ).distinct()
    res = await db.execute(stmt)
    db_cats = set(r.strip() for r in res.scalars().all() if r and r.strip())

    defaults = [
        "citizenship", "lalpurja", "gazette", "license", "certificate",
        "letter", "form", "newspaper", "photo", "passport", "court_notice",
        "tax_clearance", "voter_id", "identity_card", "other"
    ]
    all_cats = sorted(list(set(defaults).union(db_cats)))
    return {"categories": all_cats}


@router.get("/{image_id}", response_model=ImageOut)
async def get_image(image_id: int, db: AsyncSession = Depends(get_db)):
    """Fetch single image metadata."""
    stmt = select(ImageModel).where(ImageModel.id == image_id)
    res = await db.execute(stmt)
    img = res.scalars().first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    return img


@router.api_route("/{image_id}/file", methods=["GET", "HEAD"])
async def get_image_file(image_id: int, db: AsyncSession = Depends(get_db)):
    """
    Serve image binary with automatic SVG fallback:
    Never returns broken 404 to browser <img> tags.
    """
    stmt = select(ImageModel).where(ImageModel.id == image_id)
    res = await db.execute(stmt)
    img = res.scalars().first()

    if not img or not img.file_path:
        svg = generate_document_svg_placeholder(image_id, "Document", "Pending")
        return Response(content=svg, media_type="image/svg+xml")

    p = Path(img.file_path)
    if not p.exists():
        svg = generate_document_svg_placeholder(
            image_id,
            img.document_type or "Document",
            img.status or "Processing"
        )
        return Response(content=svg, media_type="image/svg+xml")

    return FileResponse(p, media_type="image/webp")


@router.patch("/{image_id}/annotate", response_model=ImageOut)
async def annotate_image_human(
    image_id: int,
    data: ImageAnnotation,
    db: AsyncSession = Depends(get_db),
):
    """
    Human annotation via frontend:
    - Automatically approved (no extra approval required for human)
    - Sets annotation_source = 'manual'
    """
    stmt = select(ImageModel).where(ImageModel.id == image_id)
    res = await db.execute(stmt)
    img = res.scalars().first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    if data.ocr_text is not None:
        img.ocr_text = data.ocr_text
        img.has_text = bool(data.ocr_text.strip())
    if data.caption_nepali is not None:
        img.caption_nepali = data.caption_nepali
    if data.caption_english is not None:
        img.caption_english = data.caption_english
    if data.annotation_text is not None:
        img.annotation_text = data.annotation_text
    if data.document_type is not None:
        img.document_type = data.document_type
    if data.ai_output is not None:
        img.ai_output = data.ai_output
    if data.language_tags is not None:
        img.language_tags = data.language_tags
    if data.tags is not None:
        img.tags = data.tags
    if data.has_text is not None:
        img.has_text = data.has_text

    img.annotation_source = "manual"
    img.annotated_by = "user"
    img.is_approved = True
    img.status = "approved"

    await db.commit()
    await db.refresh(img)
    return img


@router.post("/{image_id}/ai-assist")
async def ai_assist_image(
    image_id: int,
    data: Optional[AiAssistRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Queue this image for AI Agent / MCP annotation with top priority.
    Sets ai_requested=True and updates ai_output so external AI models pick it up first.
    """
    stmt = select(ImageModel).where(ImageModel.id == image_id)
    res = await db.execute(stmt)
    img = res.scalars().first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    img.ai_requested = True
    img.ai_requested_at = func.now()
    img.ai_output = (
        f"⏳ Queued for AI / MCP annotation with Priority 1.\n"
        f"The AI model (Antigravity / MCP Agent) will pick this document from the queue "
        f"and submit ground-truth Devanagari OCR & captions into the Gated Approval Queue."
    )

    await db.commit()
    await db.refresh(img)

    return {
        "status": "queued",
        "image_id": img.id,
        "ai_requested": True,
        "ai_output": img.ai_output,
        "message": f"Document #{img.id} queued for AI Agent / MCP processing with top priority.",
    }


@router.post("/{image_id}/skip", status_code=status.HTTP_200_OK)
async def skip_image(
    image_id: int,
    skip_data: ImageSkip,
    db: AsyncSession = Depends(get_db),
):
    """
    Skip/reject image:
    - Permanently deletes physical file to reclaim storage
    - Marks status as 'skipped'
    """
    stmt = select(ImageModel).where(ImageModel.id == image_id)
    res = await db.execute(stmt)
    img = res.scalars().first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    if img.file_path:
        Path(img.file_path).unlink(missing_ok=True)

    img.status = "skipped"
    img.skip_reason = skip_data.reason
    img.file_path = ""

    await db.commit()
    return {"message": "Image skipped and file deleted"}


@router.post("/batch-action")
async def batch_image_action(
    payload: BatchImageActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Execute bulk operations on multiple documents simultaneously."""
    if not payload.image_ids:
        raise HTTPException(status_code=400, detail="No image IDs provided")

    if payload.action == "approve":
        stmt = (
            update(ImageModel)
            .where(ImageModel.id.in_(payload.image_ids))
            .values(is_approved=True, status="annotated", annotation_source="manual")
        )
        await db.execute(stmt)
        await db.commit()
        return {"status": "ok", "action": "approve", "affected": len(payload.image_ids)}

    elif payload.action == "set_category":
        if not payload.category:
            raise HTTPException(status_code=400, detail="Category name required")
        stmt = (
            update(ImageModel)
            .where(ImageModel.id.in_(payload.image_ids))
            .values(document_type=payload.category.strip().lower())
        )
        await db.execute(stmt)
        await db.commit()
        return {"status": "ok", "action": "set_category", "affected": len(payload.image_ids), "category": payload.category}

    elif payload.action == "discard":
        stmt = select(ImageModel).where(ImageModel.id.in_(payload.image_ids))
        res = await db.execute(stmt)
        imgs = res.scalars().all()
        for img in imgs:
            if img.file_path:
                Path(img.file_path).unlink(missing_ok=True)
            img.status = "skipped"
            img.skip_reason = "batch_discard"
            img.file_path = ""
        await db.commit()
        return {"status": "ok", "action": "discard", "affected": len(imgs)}

    raise HTTPException(status_code=400, detail=f"Unsupported action: {payload.action}")


@router.post("/export")
async def export_dataset(
    approved_only: bool = Query(True),
    format_type: str = Query("jsonl", pattern="^(jsonl|json|csv|llava)$"),
    document_type: Optional[str] = Query(None),
    min_ocr_length: int = Query(0, ge=0),
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """
    Export dataset tailored for VLM (LLaVA, PaliGemma) and CLIP finetuning:
    Supports: jsonl, json, csv, and llava (conversational visual instruction format).
    Optional filters: document_type, min_ocr_length. Optional direct browser download.
    """
    import csv
    import json
    from ..config import settings

    stmt = select(ImageModel).where(ImageModel.status != "skipped", ImageModel.status != "duplicate")
    if approved_only:
        stmt = stmt.where(ImageModel.is_approved == True)
    if document_type:
        stmt = stmt.where(ImageModel.document_type == document_type.strip().lower())
    if min_ocr_length > 0:
        stmt = stmt.where(func.length(ImageModel.ocr_text) >= min_ocr_length)

    res = await db.execute(stmt)
    records = res.scalars().all()

    ext = "jsonl" if format_type == "llava" else format_type
    export_file = settings.EXPORTS_DIR / f"open_nepali_dataset_{format_type}_{len(records)}.{ext}"

    if format_type == "llava":
        with open(export_file, "w", encoding="utf-8") as f:
            for r in records:
                llava_item = {
                    "id": f"nepali_doc_{r.id}",
                    "image": r.file_path,
                    "conversations": [
                        {
                            "from": "human",
                            "value": f"<image>\nयस नेपाली दस्तावेजको प्रकार, शीर्षक र यसमा लेखिएको विवरण खुलाउनुहोस्।\n(Transcribe this Nepali document #{r.id} and provide its Devanagari ground truth.)"
                        },
                        {
                            "from": "gpt",
                            "value": f"दस्तावेज प्रकार: {r.document_type or 'दस्तावेज'}\n\n[Devanagari OCR Text]:\n{r.ocr_text or 'कुनै स्पष्ट पाठ फेला परेन'}\n\n[नेपाली क्याप्सन]:\n{r.caption_nepali or ''}\n\n[English Caption]:\n{r.caption_english or ''}"
                        }
                    ]
                }
                f.write(json.dumps(llava_item, ensure_ascii=False) + "\n")

    elif format_type == "csv":
        with open(export_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "file_path", "width", "height", "document_type", "caption_nepali", "caption_english", "ocr_text", "is_approved"])
            for r in records:
                writer.writerow([r.id, r.file_path, r.width, r.height, r.document_type or "", r.caption_nepali or "", r.caption_english or "", r.ocr_text or "", r.is_approved])

    else:
        items = []
        for r in records:
            items.append({
                "id": r.id,
                "image_path": r.file_path,
                "file_hash": r.file_hash,
                "width": r.width,
                "height": r.height,
                "has_text": r.has_text,
                "ocr_text": r.ocr_text or "",
                "caption_nepali": r.caption_nepali or "",
                "caption_english": r.caption_english or "",
                "annotation": r.annotation_text or "",
                "document_type": r.document_type or "unspecified",
                "language_tags": r.language_tags or ["nepali"],
                "tags": r.tags or [],
                "source": r.annotation_source or "manual",
            })

        with open(export_file, "w", encoding="utf-8") as f:
            if format_type == "jsonl":
                for it in items:
                    f.write(json.dumps(it, ensure_ascii=False) + "\n")
            else:
                json.dump(items, f, ensure_ascii=False, indent=2)

    if download:
        return FileResponse(
            export_file,
            filename=export_file.name,
            media_type="application/octet-stream"
        )

    return {
        "count": len(records),
        "format": format_type,
        "export_path": str(export_file),
        "filename": export_file.name,
    }
