# Setup & Seed Data Guidelines: Nepali Image Studio

This directory contains pristine curated sample datasets, unique Nepali web domain archives, and reproduction scripts tailored for academic research, supervisor verification, and quick bootstrapping of the **Nepali Image Studio** platform.

---

## Directory Structure

```
setup/
├── GUIDELINES.md                 # This comprehensive guideline document
├── unique_np_domains.json        # 9,712 unique .np domains categorized by tier (JSON format)
├── unique_np_domains.txt         # 9,712 unique .np domains as a newline-delimited list
└── sample_dataset/
    ├── approved/                 # 31 certified, verified human/AI annotated WebP images
    ├── approved_annotations.json # Complete metadata, OCR Devanagari text, captions & dimensions
    ├── unannotated/              # 10 sample unannotated WebP images ready for testing
    └── unannotated_samples.json  # Metadata for unannotated samples
```

---

## 1. Approved Dataset (`sample_dataset/approved/`)

- **Count**: 31 high-quality images.
- **Format**: Optimized WebP (`.webp`), verified dimensions, aspect ratio preserved.
- **Metadata**: Found in `sample_dataset/approved_annotations.json`.
- **Fields included for each entry**:
  - `id`: Database document ID.
  - `file_path`: Storage path on disk.
  - `filename`: Original filename.
  - `document_type`: Classified category (e.g., `citizenship`, `lalpurja`, `gazette`, `license`, `bill`, `other`).
  - `ocr_text`: Ground-truth Devanagari transcription.
  - `caption_nepali`: Native Nepali descriptive caption.
  - `caption_english`: Cross-lingual English descriptive caption.
  - `stage`: `"approved"`.
  - `is_approved`: `true`.
  - `width` / `height` / `file_size`: Geometric and physical file properties.

### Sample Approved Entry
```json
{
  "id": 77442,
  "filename": "f626a5783228d4fa.webp",
  "document_type": "banner",
  "ocr_text": "नेपाल सरकार तथा सम्बद्ध निकाय | desktop version 1366x287 (1)8d7wu | डिजिटल वेब ब्यानर",
  "caption_nepali": "नेपाल सरकार तथा सम्बद्ध निकायको आधिकारिक वेबसाइटको शीर्ष ब्यानर / सूचना स्लाइडर...",
  "caption_english": "Header banner / notice slider from the official web portal of Government of Nepal...",
  "is_approved": true,
  "stage": "approved",
  "width": 1366,
  "height": 287
}
```

---

## 2. Unannotated Sample Images (`sample_dataset/unannotated/`)

- **Count**: 10 diverse unannotated images.
- **Use Case**:
  - Direct testing of the **Multimodal Annotator Workspace** (`#view-annotate`).
  - Testing the **Google AI Studio (Gemini Vision)** in-browser direct annotation workflow.
  - Testing the **Google Lens OCR** extraction workflow.
  - Testing Model Context Protocol (**MCP**) integration with AI coding agents (Antigravity, Claude, OpenCode).

---

## 3. Discovered `.np` Domains Archive (`unique_np_domains.json` / `.txt`)

During large-scale focused web crawling across Nepal's national cyberspace, our spiders discovered and cataloged **9,712 unique `.np` second-level and top-level domain hosts**.

### Categorization Breakdown
- **`gov_np`**: Government ministries, departments, local municipalities, and constitutional commissions.
- **`edu_np`**: Tribhuvan University, Kathmandu University, affiliated colleges, schools, and educational boards.
- **`org_np`**: Non-governmental organizations, associations, cultural foundations, and civil society groups.
- **`mil_np`**: Defense and armed police services.
- **`com_np` / `other_np`**: Commercial institutions, banks, newspapers, media, and technology portals.

### JSON Schema
```json
{
  "total_unique_domains": 9712,
  "domains": [
    "nepal.gov.np",
    "moha.gov.np",
    "dop.gov.np",
    "tu.edu.np",
    "ku.edu.np"
  ],
  "breakdown": {
    "gov_np": 1420,
    "edu_np": 1180,
    "org_np": 2340,
    "other_np": 4772
  }
}
```

---

## 4. How to Bootstrap a Fresh Instance

If you are setting up this repository on a new machine or empty database:

1. **Install Prerequisites**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure Database**:
   Set `DATABASE_URL` in your `.env` file (e.g., PostgreSQL or SQLite):
   ```env
   DATABASE_URL=postgresql://user:password@localhost:5432/open_nepali_image
   ```

3. **Run Migrations**:
   ```bash
   alembic upgrade head
   ```

4. **Import Sample Dataset**:
   You can copy images from `setup/sample_dataset/approved/` and `setup/sample_dataset/unannotated/` directly into `data/processed/` and import the corresponding JSON entries using python or psql:
   ```bash
   cp setup/sample_dataset/approved/*.webp data/processed/
   cp setup/sample_dataset/unannotated/*.webp data/processed/
   ```

5. **Start Studio**:
   ```bash
   ./run.sh
   # Or directly with uvicorn
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
