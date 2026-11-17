# 🇳🇵 Nepali Image Studio (Open Nepali Image Platform)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-336791.svg)](https://www.postgresql.org/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-Integrated-purple.svg)](https://modelcontextprotocol.io/)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-v4-38B2AC.svg)](https://tailwindcss.com/)

> **An enterprise-grade, multimodal visual archive and dataset engineering studio dedicated to collecting, deduplicating, transcribing, and cataloging Nepali cultural artifacts, administrative documents, and Devanagari text.**

Developed for university research, academic evaluation, and sovereign AI dataset curation across Nepal's national cyberspace.

---

## 🌟 Key Features & Highlights

1. **Massive Focused Web Crawling**:
   - Discovered and indexed **9,712 unique `.np` domains** across government (`.gov.np`), educational (`.edu.np`), organizational (`.org.np`), and public portals.
   - Crawled over **50,000+ visual assets** with adaptive rate-limiting and domain-tier prioritization.

2. **Zero-Loss Perceptual Deduplication Pipeline**:
   - Dual-layer perceptual hashing (**pHash + dHash**) with Hamming distance filtering.
   - Geometric normalization and WebP compression for lossless storage footprint reduction.

3. **Multimodal Ground-Truth Annotator**:
   - Ergonomic 5:7 split-screen workspace with zero-latency pre-fetching and local draft persistence.
   - Integrated Devanagari Quick-Pad (numerals `०-९` and complex ligatures `ऋ, ॐ, ज्ञ, त्र, क्ष, श्र`).
   - Image inspection toolkit: Contrast enhancement, grayscale striping, negative inversion, and 90° rotation.

4. **In-Browser Client-Side AI Vision (Google AI Studio Key)**:
   - Zero-server overhead! Directly paste a Google AI Studio (Gemini) API key into the browser.
   - 1-click multimodal OCR and bilingual caption generation right on the client side.

5. **Integrated Model Context Protocol (MCP) Server**:
   - Native MCP endpoints enabling coding agents (Google Antigravity, Claude Desktop, OpenCode) to inspect images, draft annotations, and certify records directly.

6. **Google Lens Fast OCR Workflow**:
   - Seamless Chrome right-click integration to extract dense Devanagari paragraphs without complex local OCR setups.

---

## 📁 Repository Structure

```
nepali_image_studio/
├── app/
│   ├── api/                 # FastAPI routes (images, crawler, annotations, stats)
│   ├── core/                # Configuration, logging, database connection
│   ├── crawler/             # Focused spider, robots checker, HTML scraper
│   ├── mcp/                 # Model Context Protocol (MCP) server implementation
│   ├── models/              # SQLAlchemy ORM models (Image, Domain, Tag, Approval)
│   ├── pipeline/            # Deduplication, pHash/dHash, WebP processor
│   ├── static/              # CSS, JavaScript (Annotator, Dashboard, Explorer, API)
│   └── templates/           # Modular Jinja2 HTML templates and view components
├── setup/                   # Sample datasets, guidelines & 9,712 unique .np domains
│   ├── GUIDELINES.md        # Dataset schema and setup guidelines
│   ├── unique_np_domains.json # 9,712 categorized .np domains
│   ├── unique_np_domains.txt  # Plaintext list of all .np hosts
│   └── sample_dataset/      # 31 approved + 10 unannotated sample images & JSON metadata
├── alembic/                 # Database migrations
├── tests/                   # Pytest test suite
├── run.sh                   # One-click execution script
├── requirements.txt         # Production dependencies
└── README.md                # Project documentation
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10+ (macOS, Linux, or WSL2)
- PostgreSQL 14+ (or compatible SQLite / cloud database)

### 2. Environment Setup
```bash
# Clone the repository
git clone https://github.com/your-username/nepali_image_studio.git
cd nepali_image_studio

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Database Configuration
Create a `.env` file in the root directory:
```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/open_nepali_image
APP_ENV=development
DATA_DIR=./data
MAX_CPU_WORKERS=4
```

Apply database migrations:
```bash
alembic upgrade head
```

### 4. Running the Application
Launch the server using the optimized runner script:
```bash
chmod +x run.sh
./run.sh
```
Or start directly with Uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open your browser at: **`http://localhost:8000`**

---

## 🤖 AI Annotation & Google AI Studio (Gemini) Key

To allow students, evaluators, and annotators to use AI assistance **without configuring heavy local GPU hardware or exposing backend keys**, Nepali Image Studio features a **client-side AI integration**:

1. Open the **Multimodal Annotator** tab in the web interface.
2. In the AI Assistant card (top right of the left column), click **"AI Key"**.
3. Paste your free Google AI Studio API key (get one from [aistudio.google.com](https://aistudio.google.com/app/apikey)).
4. Click **"Save Key"**. The key is stored securely in your browser's `localStorage` and never transmitted to your backend database.
5. On any document, click **"Run AI Vision"**. Gemini Vision will inspect the image in real-time, generate the Devanagari OCR transcription, Nepali descriptive caption, and document category, and automatically populate the fields for your review!

> **Code Location for Hackers / Extenders**:
> Inspect `app/static/js/components/annotator.js` -> `runBrowserGeminiVision()` to customize the prompt or switch models (e.g. `gemini-2.5-flash`, `gemini-1.5-pro`).

---

## 🔍 Google Lens Manual OCR Workflow

For historical documents, complex handwritten official letters, or degraded seals where standard OCR models struggle:

1. **Right-Click Image**: In the image preview box on the left, right-click the document.
2. **Select Search Image with Google**: In Google Chrome, choose *“Search image with Google”* (or use Google Lens on a mobile device).
3. **Copy Devanagari Text**: In the Google Lens side panel, click **“Text”** → **“Select all text”** → **“Copy text”**.
4. **Paste & Polish**: Paste the transcription directly into the **“OCR Transcribed Text”** box.
5. Use the built-in **Devanagari Quick-Pad** (`ऋ, ॐ, ज्ञ, त्र, ।`) for instant punctuation fixups, and hit **Save & Approve (Alt+S)**.

---

## 🔌 Model Context Protocol (MCP) Integration

This repository includes a production-grade **Model Context Protocol (MCP)** server implemented under `app/mcp/server.py`.

### MCP Tools Provided:
- `get_next_images_to_annotate(limit, stage)`: Fetch images pending review or queued for AI processing.
- `get_image_details(image_id)`: Retrieve image file paths, dimensions, headers, and metadata.
- `submit_ai_annotation(...)`: Submit Devanagari OCR transcription and captions directly to the database.
- `search_approved_dataset(query, limit)`: Query certified dataset records for few-shot in-context learning.
- `propose_and_save_concept(...)`: Curate new visual concepts into the taxonomy.

### Connecting with Antigravity / Claude Desktop
Add the following entry to your `mcp_config.json`:
```json
{
  "mcpServers": {
    "open-nepali-image": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/absolute/path/to/nepali_image_studio",
      "env": {
        "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/open_nepali_image"
      }
    }
  }
}
```

---

## 📊 Dataset & Setup Artifacts

In the `setup/` directory, you will find:
- **`unique_np_domains.json` / `.txt`**: The comprehensive index of **9,712 unique `.np` domains** harvested during research.
- **`sample_dataset/approved/`**: 31 certified, verified ground-truth images with OCR & VLM captions (`approved_annotations.json`).
- **`sample_dataset/unannotated/`**: 10 clean test images with metadata (`unannotated_samples.json`) to verify crawling and annotation workflows immediately.
- **`setup/GUIDELINES.md`**: Technical specification and seeding documentation.

---

## 🛡️ License & Ethical Data Stewardship

All web scraping adheres strictly to `robots.txt` compliance, polite request throttling, and public domain cultural preservation. Certified records are maintained for educational and scientific research under the Open Data Initiative.
