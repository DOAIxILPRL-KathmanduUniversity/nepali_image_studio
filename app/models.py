"""SQLAlchemy ORM models for the annotation platform."""
from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index,
    Integer, String, Text, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


# ─── Discovered .np Domains ──────────────────────────────────────────────────

class CrawledDomain(Base):
    __tablename__ = "crawled_domains"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    domain = Column(String(255), unique=True, nullable=False, index=True)
    domain_tier = Column(String(32), default="other", index=True)  # gov/edu/org/mil/net/other
    discovered_at = Column(DateTime(timezone=True), default=utcnow)
    discovered_from_url = Column(Text)
    pages_crawled = Column(Integer, default=0)
    pages_discovered = Column(Integer, default=0)
    media_found = Column(Integer, default=0)
    status = Column(String(32), default="active", index=True)  # active/completed/rate_limited/error
    last_crawled_at = Column(DateTime(timezone=True))
    last_error = Column(Text)


# ─── Sources (where content came from) ───────────────────────────────────────

class Source(Base):
    __tablename__ = "sources"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    url = Column(Text, unique=True, nullable=False)
    url_hash = Column(String(128), nullable=False, index=True)
    domain = Column(String(255), nullable=False, index=True)
    domain_tier = Column(String(16), default="other")
    source_type = Column(String(32), nullable=False)  # crawl / icrawler / manual
    crawl_depth = Column(Integer, default=0)
    last_crawled_at = Column(DateTime(timezone=True))
    status = Column(String(32), default="pending", index=True)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    raw_assets = relationship("RawAsset", back_populates="source")


# ─── Raw Assets (downloaded files before processing) ─────────────────────────

class RawAsset(Base):
    __tablename__ = "raw_assets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_id = Column(BigInteger, ForeignKey("sources.id", ondelete="SET NULL"))
    asset_type = Column(String(16), nullable=False)  # image / pdf
    original_url = Column(Text)
    url_hash = Column(String(128), index=True)
    file_hash = Column(String(128), index=True)
    perceptual_hash = Column(String(128), index=True)
    file_path = Column(Text)
    file_size_bytes = Column(BigInteger)
    original_filename = Column(Text)
    mime_type = Column(String(128))
    pdf_page_count = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)
    status = Column(String(32), default="pending", index=True)
    duplicate_of_id = Column(BigInteger, ForeignKey("raw_assets.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow)

    source = relationship("Source", back_populates="raw_assets")
    images = relationship("Image", back_populates="raw_asset")


# ─── Images (processed, compressed, ready for annotation) ────────────────────

class Image(Base):
    __tablename__ = "images"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    raw_asset_id = Column(BigInteger, ForeignKey("raw_assets.id", ondelete="SET NULL"))
    source_id = Column(BigInteger, ForeignKey("sources.id", ondelete="SET NULL"))

    # File info
    file_path = Column(Text, nullable=False)
    file_hash = Column(String(128), nullable=False, index=True)
    perceptual_hash = Column(String(128), index=True)
    file_size_bytes = Column(BigInteger)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    format = Column(String(16), default="webp")

    # PDF origin
    pdf_page_number = Column(Integer)

    # OCR
    has_text = Column(Boolean, default=False)
    ocr_text = Column(Text)
    ocr_confidence = Column(Float)

    # Caption
    caption_nepali = Column(Text)
    caption_english = Column(Text)

    # Annotation
    annotation_text = Column(Text)
    ai_output = Column(Text)
    annotation_source = Column(String(32))  # manual / ai_pending / ai_approved
    annotation_metadata = Column(JSONB, default=dict)
    annotated_at = Column(DateTime(timezone=True))
    annotated_by = Column(String(64), default="user")

    # Tags & classification
    document_type = Column(String(64))
    language_tags = Column(JSONB, default=list)
    tags = Column(JSONB, default=list)

    # Lifecycle
    status = Column(String(32), default="ready", index=True)
    is_approved = Column(Boolean, default=False, index=True)
    ai_requested = Column(Boolean, default=False, index=True)
    ai_requested_at = Column(DateTime(timezone=True))
    skip_reason = Column(Text)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    raw_asset = relationship("RawAsset", back_populates="images")

    __table_args__ = (
        Index("idx_images_status_approved", "status", "is_approved"),
        Index("idx_images_annotation_source", "annotation_source"),
    )


# ─── Job Queue (PostgreSQL-native with SKIP LOCKED) ──────────────────────────

class Job(Base):
    __tablename__ = "job_queue"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_type = Column(String(64), nullable=False, index=True)
    payload = Column(JSONB, nullable=False, default=dict)
    priority = Column(Integer, default=5)
    status = Column(String(32), default="pending")
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    error_message = Column(Text)
    locked_by = Column(String(128))
    locked_at = Column(DateTime(timezone=True))
    run_after = Column(DateTime(timezone=True), default=utcnow)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_queue_fetch", "status", "priority", "run_after"),
    )


# ─── Crawl State & Frontier ──────────────────────────────────────────────────

class CrawlFrontier(Base):
    __tablename__ = "crawl_frontier"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    url = Column(Text, unique=True, nullable=False)
    url_hash = Column(String(128), unique=True, nullable=False, index=True)
    domain = Column(String(255), nullable=False, index=True)
    depth = Column(Integer, default=0)
    discovered_from = Column(Text)
    # Status: pending → crawling → done (NEVER crawled again once done) → error
    status = Column(String(32), default="pending", index=True)
    attempts = Column(Integer, default=0)
    crawled_at = Column(DateTime(timezone=True))
    last_attempted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("idx_frontier_domain_status", "domain", "status"),
        Index("idx_frontier_depth_status", "depth", "status"),
    )


class CrawlSession(Base):
    __tablename__ = "crawl_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(Text)
    seed_urls = Column(JSONB, nullable=False)
    config = Column(JSONB, default=dict)
    status = Column(String(32), default="idle")
    stats = Column(JSONB, default=dict)
    started_at = Column(DateTime(timezone=True))
    paused_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)


# ─── Duplicate Groups ────────────────────────────────────────────────────────

class DuplicateGroup(Base):
    __tablename__ = "duplicate_groups"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    canonical_image_id = Column(BigInteger, ForeignKey("images.id"))
    member_count = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    members = relationship("DuplicateMember", back_populates="group")


class DuplicateMember(Base):
    __tablename__ = "duplicate_members"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("duplicate_groups.id", ondelete="CASCADE"))
    image_id = Column(BigInteger, ForeignKey("images.id", ondelete="CASCADE"))
    similarity_score = Column(Float)
    is_canonical = Column(Boolean, default=False)

    group = relationship("DuplicateGroup", back_populates="members")


# ─── App Settings ────────────────────────────────────────────────────────────

class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(128), primary_key=True)
    value = Column(JSONB, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ─── Saved Concepts (AI Concept Studio & Ingestion Library) ───────────────────

class SavedConcept(Base):
    __tablename__ = "saved_concepts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    topic = Column(String(255), nullable=False)
    document_type = Column(String(64), default="other", index=True)
    caption_nepali = Column(Text, nullable=False)
    search_query_en = Column(Text, nullable=False)
    alternative_queries = Column(JSONB, default=list)
    tags = Column(JSONB, default=list)
    is_downloaded = Column(Boolean, default=False, index=True)
    images_downloaded_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

