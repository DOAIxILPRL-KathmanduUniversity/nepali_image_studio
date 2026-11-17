"""Extract .np domains from top10milliondomains.csv and seed them gradually into PostgreSQL."""
import asyncio
import csv
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from app.config import settings
from app.database import init_db, AsyncSessionLocal
from app.models import CrawledDomain, CrawlFrontier
from app.services.dedup_service import dedup_service
from app.services.domain_harvester import domain_harvester
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, func

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_importer")

CSV_PATH = Path("/Users/paramanada/Desktop/open_nepali_image/top10milliondomains.csv")
SEEDS_OUT = Path(__file__).resolve().parent.parent / "app" / "seeds" / "top_np_domains.json"


def extract_np_domains_from_csv(csv_path: Path) -> List[Dict[str, Any]]:
    """Scan top10milliondomains.csv and extract all domains ending in .np."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found at {csv_path}")

    logger.info(f"Reading {csv_path}...")
    np_domains = []
    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) >= 2:
                domain = row[1].strip().lower()
                if domain.endswith(".np") and len(domain) > 3:
                    rank = int(row[0]) if row[0].isdigit() else 9999999
                    opr = float(row[3]) if len(row) > 3 and row[3] else 0.0
                    tier = domain_harvester.classify_tier(domain)
                    np_domains.append({
                        "rank": rank,
                        "domain": domain,
                        "tier": tier,
                        "open_page_rank": opr,
                    })

    # Sort primarily by tier priority (gov -> edu -> org -> mil -> net -> com -> other), then by rank
    tier_order = {"gov": 1, "edu": 2, "org": 3, "mil": 3, "net": 4, "com": 5, "other": 6}
    np_domains.sort(key=lambda x: (tier_order.get(x["tier"], 9), x["rank"]))
    logger.info(f"Extracted {len(np_domains)} valid .np domains.")
    return np_domains


async def import_and_seed_domains(
    domains: List[Dict[str, Any]],
    batch_size: int = 100,
    seed_frontier: bool = True,
    delay_between_batches: float = 0.05,
):
    """Gradually seed domains into crawled_domains and crawl_frontier in manageable batches."""
    await init_db()

    total = len(domains)
    logger.info(f"Starting gradual database ingestion for {total} domains (batch_size={batch_size})...")

    # Save to JSON seed file
    SEEDS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEDS_OUT, "w", encoding="utf-8") as f:
        json.dump({"total": total, "domains": domains}, f, indent=2)
    logger.info(f"Saved domain directory to {SEEDS_OUT}")

    total_inserted_domains = 0
    total_seeded_frontier = 0

    for i in range(0, total, batch_size):
        chunk = domains[i : i + batch_size]

        async with AsyncSessionLocal() as db:
            for item in chunk:
                domain = item["domain"]
                tier = item["tier"]

                # 1. Upsert into crawled_domains
                domain_stmt = pg_insert(CrawledDomain).values(
                    domain=domain,
                    domain_tier=tier,
                    discovered_from_url="top10milliondomains.csv",
                    status="active",
                ).on_conflict_do_nothing(index_elements=["domain"])

                res_domain = await db.execute(domain_stmt)
                if res_domain.rowcount > 0:
                    total_inserted_domains += 1

                # 2. Seed root URL into crawl_frontier
                if seed_frontier:
                    root_url = f"https://{domain}/"
                    url_h = dedup_service.compute_url_hash(root_url)

                    front_stmt = pg_insert(CrawlFrontier).values(
                        url=root_url,
                        url_hash=url_h,
                        domain=domain,
                        depth=0,
                        discovered_from="top10milliondomains_seed",
                        status="pending",
                    ).on_conflict_do_nothing(index_elements=["url_hash"])

                    res_front = await db.execute(front_stmt)
                    if res_front.rowcount > 0:
                        total_seeded_frontier += 1

            await db.commit()

        pct = min(100.0, (i + len(chunk)) / total * 100)
        logger.info(f"Progress: {i + len(chunk)}/{total} ({pct:.1f}%) | Harvested: {total_inserted_domains} | Frontier: {total_seeded_frontier}")
        if delay_between_batches > 0:
            await asyncio.sleep(delay_between_batches)

    # Final summary
    async with AsyncSessionLocal() as db:
        c_dom = (await db.execute(select(func.count(CrawledDomain.id)))).scalar_one()
        c_front = (await db.execute(select(func.count(CrawlFrontier.id)))).scalar_one()
        logger.info(f"Completed! Total CrawledDomain rows: {c_dom}, CrawlFrontier rows: {c_front}")


def main():
    domains = extract_np_domains_from_csv(CSV_PATH)
    asyncio.run(import_and_seed_domains(domains))


if __name__ == "__main__":
    main()
