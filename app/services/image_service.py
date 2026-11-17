"""Image processing service: A4-max resizing, WebP compression, RGB normalization."""
import os
from pathlib import Path
from typing import Optional, Dict, Any
from PIL import Image, ImageOps
from ..config import settings
from .dedup_service import dedup_service


class ImageService:
    """Processes images with memory-conscious constraints for 8GB Mac."""

    def __init__(self):
        self.max_dimension = settings.MAX_IMAGE_DIMENSION  # 2480px (A4 @ 300DPI)
        self.webp_quality = settings.WEBP_QUALITY          # 85
        self.min_bytes = settings.MIN_IMAGE_SIZE_BYTES     # 5000 bytes

    def process_and_compress(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        filename_prefix: str = "img",
    ) -> Optional[Dict[str, Any]]:
        """
        Validate, resize to A4 maximum, normalize to RGB, and save as WebP.
        Returns metadata dict or None if invalid/skipped.
        """
        input_p = Path(input_path)
        if not input_p.exists():
            return None

        # Filter out tiny icon-like files by byte size
        if input_p.stat().st_size < self.min_bytes:
            return None

        try:
            with Image.open(input_p) as img:
                # Transpose according to EXIF orientation if present
                img = ImageOps.exif_transpose(img)

                width, height = img.size

                # Skip tiny dimensions (e.g. tracking pixels or tiny icons)
                if width < 80 or height < 80:
                    return None

                # Resize if exceeding A4 maximum
                max_side = max(width, height)
                if max_side > self.max_dimension:
                    scale = self.max_dimension / float(max_side)
                    new_w = max(1, int(width * scale))
                    new_h = max(1, int(height * scale))
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    width, height = new_w, new_h

                # Normalize color format
                if img.mode in ("RGBA", "LA", "P"):
                    # Convert transparent images cleanly onto white background
                    rgba = img.convert("RGBA")
                    bg = Image.new("RGB", rgba.size, (255, 255, 255))
                    bg.paste(rgba, mask=rgba.split()[3])
                    img = bg
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Ensure output directory exists
                out_d = Path(output_dir)
                out_d.mkdir(parents=True, exist_ok=True)

                # Compute preliminary file hash to produce deterministic output name
                stem = f"{filename_prefix}_{input_p.stem}"
                out_file = out_d / f"{stem}.webp"

                # Save compressed WebP
                img.save(out_file, "WEBP", quality=self.webp_quality, method=4)

            # Compute hashes on the processed output file
            file_hash = dedup_service.compute_file_hash(out_file)
            p_hash = dedup_service.compute_perceptual_hash(out_file)
            file_size = out_file.stat().st_size

            # Rename to hash-based filename for clean storage
            final_file = out_d / f"{file_hash[:16]}.webp"
            if out_file != final_file:
                out_file.replace(final_file)

            return {
                "file_path": str(final_file),
                "file_hash": file_hash,
                "perceptual_hash": p_hash,
                "file_size_bytes": file_size,
                "width": width,
                "height": height,
                "format": "webp",
            }
        except Exception:
            return None


image_service = ImageService()
