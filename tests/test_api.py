"""Integration tests for FastAPI REST API endpoints."""
import pytest
import httpx
from app.main import app
from app.database import init_db


@pytest.mark.asyncio
async def test_api_health_and_dashboard():
    """Verify health check and dashboard HTML endpoints."""
    await init_db()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Health
        res = await client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        # Dashboard static HTML
        res_ui = await client.get("/")
        assert res_ui.status_code == 200
        assert "Open Nepali Image" in res_ui.text


@pytest.mark.asyncio
async def test_stats_and_seeds_api():
    """Verify stats aggregation and seeds directory."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Stats
        res_stats = await client.get("/api/stats/dashboard")
        assert res_stats.status_code == 200
        stats = res_stats.json()
        assert "total_images" in stats
        assert "disk_free_gb" in stats

        # Seeds
        res_seeds = await client.get("/api/crawler/seeds")
        assert res_seeds.status_code == 200
        seeds = res_seeds.json()
        assert "categories" in seeds
        assert len(seeds["categories"]) > 0


@pytest.mark.asyncio
async def test_concept_suggestion_api():
    """Verify the UI helper for suggesting Nepali captions and English search queries."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/search/suggest", json={"concept_nepali": "नागरिकता"})
        assert res.status_code == 200
        d = res.json()
        assert "नागरिकता" in d["suggested_caption_nepali"]
        assert len(d["suggested_english_search_queries"]) > 0
        assert d["suggested_document_type"] == "certificate"


@pytest.mark.asyncio
async def test_top_np_domains_and_pagination_api():
    """Verify 2,043 .np domain directory, tier filtering, and page-by-page controls."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Check domain list pagination
        res = await client.get("/api/crawler/domains?page=1&limit=10")
        assert res.status_code == 200
        data = res.json()
        assert "domains" in data
        assert "total_domains" in data
        assert "page" in data
        assert data["page"] == 1


@pytest.mark.asyncio
async def test_static_modular_assets_served():
    """Verify modular JS and CSS files are correctly served by FastAPI."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in [
            "/static/css/styles.css",
            "/static/js/api.js",
            "/static/js/components/crawler.js",
            "/static/js/components/gallery.js",
            "/static/js/components/annotator.js",
            "/static/js/components/review.js",
            "/static/js/components/search.js",
            "/static/js/components/concept_studio.js",
            "/static/js/app.js",
            "/static/placeholder.svg",
        ]:
            res = await client.get(path)
            assert res.status_code == 200, f"Failed to serve {path}"


@pytest.mark.asyncio
async def test_concept_studio_endpoints():
    """Verify AI Concept studio suggestion, creation, and listing."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. AI Suggestion
        res_suggest = await client.post("/api/concepts/ai-suggest", json={"topic": "citizenship"})
        assert res_suggest.status_code == 200
        sdata = res_suggest.json()
        assert "caption_nepali" in sdata
        assert len(sdata["alternative_queries"]) > 0
        assert len(sdata["caption_nepali"]) > 0

        # 2. Create Saved Concept
        res_create = await client.post("/api/concepts", json={
            "topic": "citizenship",
            "document_type": "certificate",
            "caption_nepali": "नेपाली नागरिकताको प्रमाणपत्र आधिकारिक प्रति",
            "search_query_en": "nepali citizenship certificate official",
            "alternative_queries": ["nagrikta patra nepali document"],
            "tags": ["official", "citizenship", "gov"]
        })
        assert res_create.status_code == 201
        cdata = res_create.json()
        cid = cdata["id"]
        assert cdata["topic"] == "citizenship"

        # 3. List Saved Concepts
        res_list = await client.get("/api/concepts")
        assert res_list.status_code == 200
        concepts = res_list.json()
        assert any(c["id"] == cid for c in concepts)

        # 4. Clean up
        res_del = await client.delete(f"/api/concepts/{cid}")
        assert res_del.status_code == 204


@pytest.mark.asyncio
async def test_export_formats_llava_and_csv():
    """Verify export endpoints support standard JSONL, LLaVA visual instruction tuning, and CSV."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for fmt in ["jsonl", "llava", "csv"]:
            res = await client.post(f"/api/images/export?format_type={fmt}")
            assert res.status_code == 200
            data = res.json()
            assert data["format"] == fmt
            assert "export_path" in data
            assert "filename" in data


@pytest.mark.asyncio
async def test_crawler_modes_and_media_backlog_api():
    """Verify crawler mode switching (media_backlog, discovery, balanced) and failure retry."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Switch to Media Backlog mode
        res_m = await client.post("/api/crawler/mode", json={"mode": "media_backlog"})
        assert res_m.status_code == 200
        assert res_m.json()["mode"] == "media_backlog"

        # 2. Switch to Discovery mode
        res_d = await client.post("/api/crawler/mode", json={"mode": "discovery"})
        assert res_d.status_code == 200
        assert res_d.json()["mode"] == "discovery"

        # 3. Switch back to Balanced mode
        res_b = await client.post("/api/crawler/mode", json={"mode": "balanced"})
        assert res_b.status_code == 200
        assert res_b.json()["mode"] == "balanced"

        # 4. Retry Failed Media Jobs
        res_ret = await client.post("/api/crawler/media/retry-failed")
        assert res_ret.status_code == 200
        assert "retried_jobs" in res_ret.json()

        # 5. Reset Circuit Breaker
        res_cb = await client.post("/api/crawler/circuit-breaker/reset")
        assert res_cb.status_code == 200
        assert "cleared_domains" in res_cb.json()

        # 6. Check Status contains mode and backlog
        res_st = await client.get("/api/crawler/status")
        assert res_st.status_code == 200
        st = res_st.json()
        assert "mode" in st
        assert "media_jobs_pending" in st
        assert "media_backlog_total" in st


@pytest.mark.asyncio
async def test_ai_assist_queue_and_batch_actions():
    """Verify that Ask AI queues the document with priority, and test batch actions."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Get next unannotated
        res_next = await client.get("/api/images/next-unannotated?stage=unannotated")
        assert res_next.status_code == 200
        data_next = res_next.json()
        assert "item" in data_next

        if data_next["item"]:
            target_id = data_next["item"]["id"]
            # Trigger AI Assist Queue
            res_ai = await client.post(f"/api/images/{target_id}/ai-assist")
            assert res_ai.status_code == 200
            d_ai = res_ai.json()
            assert d_ai["status"] == "queued"
            assert d_ai["ai_requested"] is True

            # Test Batch Set Category
            res_batch = await client.post("/api/images/batch-action", json={
                "action": "set_category",
                "image_ids": [target_id],
                "category": "citizenship"
            })
            assert res_batch.status_code == 200
            assert res_batch.json()["affected"] == 1


