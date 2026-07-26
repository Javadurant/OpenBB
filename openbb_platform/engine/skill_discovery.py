"""
engine/skill_discovery.py — Skills/MCPs Discovery Engine (Project B)

Scans multiple sources daily:
1. Official MCP registry (GitHub modelcontextprotocol/registry)
2. Awesome-lists (awesome-claude-skills, awesome-agent-skills)
3. Local GitHub directory (auto-resolved from repo layout; override via $SENTRIQ_GITHUB_ROOT)

Extracts: name, description, URL, stars, tags
Stores in SQLite for future scoring + suggestions
"""

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlopen

logger = logging.getLogger("QuantEdge.SkillDiscovery")

SKILLS_DB = Path.home() / ".quantedge_skills.db"  # Persistent skills cache


class SkillRecord:
    """Single skill/MCP record"""
    def __init__(
        self,
        name: str,
        description: str,
        url: str,
        source: str,  # "mcp_registry", "awesome_list", "github"
        stars: int = 0,
        tags: Optional[List[str]] = None,
    ):
        self.name = name
        self.description = description
        self.url = url
        self.source = source
        self.stars = stars
        self.tags = tags or []
        self.discovered_at = datetime.now(timezone.utc).isoformat()


def init_skills_db() -> None:
    """Create skills database if missing"""
    conn = sqlite3.connect(SKILLS_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            url TEXT,
            source TEXT,
            stars INTEGER DEFAULT 0,
            tags TEXT,
            discovered_at TEXT,
            suggested_count INTEGER DEFAULT 0,
            dismissed INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
    logger.info(f"Skills DB ready at {SKILLS_DB}")


def discover_from_mcp_registry() -> List[SkillRecord]:
    """Scan official MCP registry for trading-relevant MCPs"""
    records = []
    try:
        # Official MCP registry (sample entries — would fetch real JSON in production)
        registry_url = "https://raw.githubusercontent.com/modelcontextprotocol/registry/main/servers.json"
        logger.info("Fetching MCP registry...")
        # For now, return placeholder; in production, urlopen(registry_url) → parse JSON
        sample_registries = [
            SkillRecord(
                name="alpaca-mcp-server",
                description="Trade stocks, ETFs, crypto via Claude",
                url="https://github.com/alpaca/alpaca-mcp-server",
                source="mcp_registry",
                stars=722,
                tags=["trading", "stocks", "alpaca", "broker"],
            ),
            SkillRecord(
                name="tradingview-mcp",
                description="Real-time charts, alerts, watchlists from TradingView",
                url="https://github.com/tradesdontlie/tradingview-mcp",
                source="mcp_registry",
                stars=2765,
                tags=["trading", "charts", "indicators", "real-time"],
            ),
            SkillRecord(
                name="sec-edgar-mcp",
                description="SEC EDGAR filings (10-K, 10-Q, 8-K) for fundamental analysis",
                url="https://github.com/stefanoamorelli/sec-edgar-mcp",
                source="mcp_registry",
                stars=263,
                tags=["trading", "fundamental", "sec", "filings"],
            ),
        ]
        records.extend(sample_registries)
        logger.info(f"Discovered {len(sample_registries)} MCPs from registry")
    except Exception as e:
        logger.warning(f"Failed to fetch MCP registry: {e}")
    return records


def discover_from_awesome_lists() -> List[SkillRecord]:
    """Scan GitHub awesome-lists for trading-relevant skills"""
    records = []
    awesome_repos = [
        ("ComposioHQ/awesome-claude-skills", "Claude skills repository"),
        ("modelcontextprotocol/servers", "Official MCP server collection"),
    ]
    
    for repo, description in awesome_repos:
        try:
            # In production, fetch repo + parse README
            # For now, use placeholder
            logger.info(f"Scanning {repo}...")
            # Would parse markdown here
        except Exception as e:
            logger.warning(f"Failed to scan {repo}: {e}")
    
    return records


def discover_from_local_github() -> List[SkillRecord]:
    """Scan user's GitHub directory for installed skills/repos"""
    records = []
    # Resolve the local GitHub projects dir dynamically so this is portable across
    # machines / CI. This file lives at <GitHub>/OpenBB/openbb_platform/engine/,
    # so parents[3] == <GitHub>. Override with $SENTRIQ_GITHUB_ROOT when the layout
    # differs (e.g. a CI checkout path).
    env_root = os.getenv("SENTRIQ_GITHUB_ROOT", "").strip()
    github_dir = Path(env_root) if env_root else Path(__file__).resolve().parents[3]

    if not github_dir.is_dir():
        logger.info("Local GitHub dir not found at %s; skipping local scan", github_dir)
        return records

    try:
        for repo_dir in github_dir.iterdir():
            if not repo_dir.is_dir():
                continue
            
            readme = repo_dir / "README.md"
            package_json = repo_dir / "package.json"
            
            if readme.exists():
                content = readme.read_text()[:500]
                records.append(SkillRecord(
                    name=repo_dir.name,
                    description=content.split('\n')[0][:200],
                    url=str(repo_dir),
                    source="github",
                    stars=0,  # Local repos
                    tags=["local"],
                ))
            elif package_json.exists():
                try:
                    pkg = json.loads(package_json.read_text())
                    records.append(SkillRecord(
                        name=pkg.get("name", repo_dir.name),
                        description=pkg.get("description", ""),
                        url=str(repo_dir),
                        source="github",
                        stars=0,
                        tags=pkg.get("keywords", []),
                    ))
                except json.JSONDecodeError:
                    pass
        
        logger.info(f"Discovered {len(records)} local repos")
    except Exception as e:
        logger.warning(f"Failed to scan local GitHub: {e}")
    
    return records


def save_skills_to_db(records: List[SkillRecord]) -> int:
    """Persist discovered skills to SQLite"""
    init_skills_db()
    conn = sqlite3.connect(SKILLS_DB)
    saved = 0
    
    for rec in records:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO skills
                (name, description, url, source, stars, tags, discovered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                rec.name,
                rec.description,
                rec.url,
                rec.source,
                rec.stars,
                json.dumps(rec.tags),
                rec.discovered_at,
            ))
            saved += 1
        except sqlite3.IntegrityError:
            pass  # Already exists
    
    conn.commit()
    conn.close()
    logger.info(f"Saved {saved} skills to DB")
    return saved


def discover_all() -> int:
    """Run all discovery sources"""
    all_records = []
    
    logger.info("Starting skill discovery...")
    all_records.extend(discover_from_mcp_registry())
    all_records.extend(discover_from_awesome_lists())
    all_records.extend(discover_from_local_github())
    
    # Deduplicate by name
    seen = set()
    deduped = []
    for rec in all_records:
        if rec.name not in seen:
            deduped.append(rec)
            seen.add(rec.name)
    
    saved = save_skills_to_db(deduped)
    logger.info(f"Discovery complete: {len(deduped)} unique skills, {saved} saved")
    return saved


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    discover_all()
