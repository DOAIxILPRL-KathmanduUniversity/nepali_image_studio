"""PDF extraction service: converts multi-page PDFs to individual images using PyMuPDF."""
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Any, Optional
from ..config import settings


class PDFService:
    """Extracts PDF pages as high-resolution images within memory budget."""

    def __init__(self, target_dpi: int = 150):
        self.target_dpi = target_dpi  # 150 DPI produces clear Devanagari text under 1MB per page

    def get_pdf_page_count(self, pdf_path: str | Path) -> int:
        """Return total page count of PDF without full loading."""
        try:
            with fitz.open(pdf_path) as doc:
                return len(doc)
        except Exception:
            return 0

    def extract_pages(
        self,
        pdf_path: str | Path,
        temp_dir: str | Path,
        max_pages: Optional[int] = 50,  # Safeguard for enormous gazette books
    ) -> List[Dict[str, Any]]:
        """
        Extract each PDF page as an image to temp_dir.
        Returns list of {page_number, temp_image_path, width, height}.
        """
        pdf_p = Path(pdf_path)
        if not pdf_p.exists():
            return []

        out_d = Path(temp_dir)
        out_d.mkdir(parents=True, exist_ok=True)

        extracted = []
        try:
            doc = fitz.open(pdf_p)
            total_pages = len(doc)
            limit = min(total_pages, max_pages) if max_pages else total_pages

            zoom = self.target_dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)

            for page_num in range(limit):
                try:
                    page = doc.load_page(page_num)
                    pix = page.get_pixmap(matrix=mat, alpha=False)

                    out_path = out_d / f"{pdf_p.stem}_p{page_num + 1}.png"
                    pix.save(str(out_path))

                    extracted.append({
                        "page_number": page_num + 1,
                        "temp_image_path": str(out_path),
                        "width": pix.width,
                        "height": pix.height,
                    })
                    # Free pixmap memory immediately
                    pix = None
                except Exception:
                    continue

            doc.close()
        except Exception:
            pass

        return extracted


pdf_service = PDFService()
