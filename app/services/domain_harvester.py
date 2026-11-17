"""Domain Harvester: Discovers and catalogs every unique .np domain across all crawled pages."""
import re
from typing import Set, List, Dict, Any, Optional
from urllib.parse import urlparse
from yarl import URL
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import CrawledDomain, CrawlFrontier
from .dedup_service import dedup_service

# Strict pattern for valid .np domains (all valid Nepal subdomains and TLD variations)
NP_DOMAIN_REGEX = re.compile(
    r'\b(?:https?://)?((?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+np)\b',
    re.IGNORECASE
)


class DomainHarvester:
    """Extracts, categorizes, and tracks every .np domain in the wild."""

    @staticmethod
    def extract_domains_from_text(html_text: str) -> Set[str]:
        """Harvest all .np domain names mentioned in HTML, text, scripts, or attributes."""
        found = set()
        for m in NP_DOMAIN_REGEX.finditer(html_text):
            raw = m.group(0).lower().strip()
            # Clean protocol prefix if present
            if raw.startswith("http://"):
                raw = raw[7:]
            elif raw.startswith("https://"):
                raw = raw[8:]
            # Strip trailing slash or path
            raw = raw.split("/")[0].split(":")[0]
            if raw.endswith(".np") and len(raw) > 3:
                found.add(raw)
        return found

    @staticmethod
    def classify_tier(domain: str) -> str:
        """Categorize domain tier."""
        d = domain.lower()
        if d.endswith(".gov.np"):
            return "gov"
        if d.endswith(".edu.np"):
            return "edu"
        if d.endswith(".org.np"):
            return "org"
        if d.endswith(".mil.np"):
            return "mil"
        if d.endswith(".net.np"):
            return "net"
        if d.endswith(".com.np") or d.endswith(".co.np"):
            return "com"
        return "other"

    async def record_and_seed_domains(
        self,
        db: AsyncSession,
        domains: Set[str],
        discovered_from_url: str,
    ) -> List[str]:
        """
        Record newly discovered .np domains in crawled_domains and inject their
        root URLs into crawl_frontier so they are automatically crawled.
        Returns list of newly discovered domains.
        """
        new_domains = []
        for domain in domains:
            tier = self.classify_tier(domain)
            # Upsert into crawled_domains
            ins_stmt = pg_insert(CrawledDomain).values(
                domain=domain,
                domain_tier=tier,
                discovered_from_url=discovered_from_url,
                status="active",
            ).on_conflict_do_nothing(index_elements=["domain"])

            res = await db.execute(ins_stmt)
            if res.rowcount > 0:
                new_domains.append(domain)
                # Seed root HTTPS URL into frontier with depth 0
                root_url = f"https://{domain}"
                root_hash = dedup_service.compute_url_hash(root_url)

                front_stmt = pg_insert(CrawlFrontier).values(
                    url=root_url,
                    url_hash=root_hash,
                    domain=domain,
                    depth=0,
                    discovered_from=discovered_from_url,
                    status="pending",
                ).on_conflict_do_nothing()
                await db.execute(front_stmt)

        if new_domains:
            await db.commit()
        return new_domains


domain_harvester = DomainHarvester()
