"""Pydantic schemas for API request/response validation."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


# ─── Image Schemas ────────────────────────────────────────────────────────────

class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_path: str
    file_hash: str
    file_size_bytes: Optional[int] = None
    width: int
    height: int
    format: str = "webp"
    pdf_page_number: Optional[int] = None
    has_text: bool = False
    ocr_text: Optional[str] = None
    caption_nepali: Optional[str] = None
    caption_english: Optional[str] = None
    annotation_text: Optional[str] = None
    ai_output: Optional[str] = None
    annotation_source: Optional[str] = None
    annotation_metadata: Optional[dict] = None
    document_type: Optional[str] = None
    language_tags: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    status: str
    is_approved: bool = False
    ai_requested: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None


class ImageAnnotation(BaseModel):
    ocr_text: Optional[str] = None
    caption_nepali: Optional[str] = None
    caption_english: Optional[str] = None
    annotation_text: Optional[str] = None
    ai_output: Optional[str] = None
    document_type: Optional[str] = None
    language_tags: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    has_text: Optional[bool] = None


class ImageSkip(BaseModel):
    reason: str = "not relevant"


class ImageFilter(BaseModel):
    status: Optional[str] = None
    is_approved: Optional[bool] = None
    has_annotation: Optional[bool] = None
    annotation_source: Optional[str] = None
    document_type: Optional[str] = None
    search_text: Optional[str] = None
    page: int = 1
    per_page: int = 50


# ─── Crawl Schemas ────────────────────────────────────────────────────────────

class CrawlStart(BaseModel):
    name: Optional[str] = None
    seed_urls: list[str]
    max_depth: int = 3
    rate_limit_ms: int = 1000
    max_concurrent: int = 5


class CrawlSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str] = None
    seed_urls: list[str]
    config: Optional[dict] = None
    status: str
    stats: Optional[dict] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


# ─── Queue Schemas ────────────────────────────────────────────────────────────

class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    payload: dict
    priority: int
    status: str
    attempts: int
    error_message: Optional[str] = None
    created_at: datetime


class QueueStats(BaseModel):
    total: int = 0
    pending: int = 0
    processing: int = 0
    done: int = 0
    error: int = 0
    dead: int = 0
    by_type: dict = {}


# ─── Search/iCrawler Schemas ─────────────────────────────────────────────────

class ICrawlerSearch(BaseModel):
    query_nepali: str
    query_english: Optional[str] = None
    max_images: int = Field(default=20, ge=1, le=100)
    engine: str = Field(default="google", pattern="^(google|bing)$")


# ─── MCP Annotation Schemas ──────────────────────────────────────────────────

class MCPAnnotation(BaseModel):
    image_id: int
    ocr_text: Optional[str] = None
    caption_nepali: Optional[str] = None
    caption_english: Optional[str] = None
    annotation_text: Optional[str] = None
    ai_output: Optional[str] = None
    document_type: Optional[str] = None
    language_tags: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    has_text: Optional[bool] = None


class MCPBatchAnnotation(BaseModel):
    annotations: list[MCPAnnotation]


# ─── Review Schemas ───────────────────────────────────────────────────────────

class ReviewAction(BaseModel):
    action: str = Field(pattern="^(approve|reject|edit)$")
    edited_text: Optional[str] = None
    edited_caption_nepali: Optional[str] = None
    edited_caption_english: Optional[str] = None


# ─── Stats / Dashboard ───────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_images: int = 0
    pending_images: int = 0
    annotated_images: int = 0
    approved_images: int = 0
    skipped_images: int = 0
    ai_pending_review: int = 0
    total_crawl_sessions: int = 0
    active_crawls: int = 0
    queue_depth: int = 0
    disk_usage_gb: float = 0.0
    disk_free_gb: float = 0.0


# ─── Settings ─────────────────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    key: str
    value: dict


# ─── Saved Concepts (AI Concept Studio) ──────────────────────────────────────

class SavedConceptCreate(BaseModel):
    topic: str
    document_type: str = "other"
    caption_nepali: str
    search_query_en: str
    alternative_queries: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class SavedConceptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic: str
    document_type: str
    caption_nepali: str
    search_query_en: str
    alternative_queries: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    is_downloaded: bool = False
    images_downloaded_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None


class AiConceptSuggestRequest(BaseModel):
    topic: Optional[str] = None


class AiConceptSuggestResponse(BaseModel):
    topic: str
    document_type: str
    caption_nepali: str
    search_query_en: str
    alternative_queries: list[str]
    tags: list[str]

