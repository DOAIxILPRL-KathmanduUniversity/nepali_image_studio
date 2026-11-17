"""Configuration for Open Nepali Image platform."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ONI_", env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://paramanada@localhost/open_nepali_image"
    DATABASE_URL_SYNC: str = "postgresql://paramanada@localhost/open_nepali_image"
    TEST_DATABASE_URL: str = "postgresql+asyncpg://paramanada@localhost/open_nepali_image_test"

    # Paths
    DATA_DIR: Path = BASE_DIR / "data"
    RAW_DIR: Path = BASE_DIR / "data" / "raw"
    RAW_IMAGES_DIR: Path = BASE_DIR / "data" / "raw" / "images"
    RAW_PDFS_DIR: Path = BASE_DIR / "data" / "raw" / "pdfs"
    PROCESSED_DIR: Path = BASE_DIR / "data" / "processed"
    EXPORTS_DIR: Path = BASE_DIR / "data" / "exports"

    # Image processing
    MAX_IMAGE_DIMENSION: int = 2480  # A4 at 300 DPI
    WEBP_QUALITY: int = 85
    MIN_IMAGE_SIZE_BYTES: int = 5000  # Skip tiny images

    # High-Throughput Crawler & Harvester
    CRAWLER_WORKERS: int = 15          # 10 to 20 concurrent coroutines
    QUEUE_WORKERS: int = 20            # 10 to 20 queue workers (SKIP LOCKED)
    CPU_PROCESS_WORKERS: int = 5       # Multiprocess CPU pool for A4 resize & PDF render
    FRONTIER_BATCH_SIZE: int = 50      # Fetch 50 URLs per frontier cycle
    CRAWLER_MAX_DEPTH: int = 4         # Deep exploration of discovered .np sites
    CRAWLER_RATE_LIMIT_MS: int = 800   # Per-domain rate limit
    CRAWLER_USER_AGENT: str = "OpenNepaliImage/1.0 (Research Crawler; +https://github.com/open-nepali-image)"
    ALLOWED_DOMAINS: list[str] = [".gov.np", ".edu.np", ".org.np", ".mil.np", ".net.np", ".np"]

    # Queue & Memory Safeguard
    QUEUE_POLL_INTERVAL: float = 0.5
    QUEUE_MAX_ATTEMPTS: int = 3
    MEMORY_SAFETY_THRESHOLD_MB: int = 600

    # Cleanup
    MAX_STORAGE_GB: int = 30
    DELETE_SKIPPED: bool = True
    DELETE_RAW_AFTER_PROCESSING: bool = True

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:3000"

settings = Settings()

# Ensure directories exist
for d in [settings.RAW_IMAGES_DIR, settings.RAW_PDFS_DIR, settings.PROCESSED_DIR, settings.EXPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)
