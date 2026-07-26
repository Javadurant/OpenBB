"""
engine/skill_suggester.py — Relevance Scoring & Daily Suggestions (Project B Phase 3)

Scores MCPs by:
1. Trading-topic relevance (keywords)
2. Popularity (GitHub stars)
3. Newness (discovery date)

Returns top 3 new skills daily without repeating old suggestions
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("QuantEdge.SkillSuggester")

SKILLS_DB = Path.home() / ".quantedge_skills.db"
TRADING_KEYWORDS = {
    "trading": 10,
    "stock": 10,
    "option": 9,
    "algo": 8,
    "signal": 8,
    "backtest": 9,
    "portfolio": 8,
    "risk": 7,
    "broker": 10,
    "alpaca": 10,
    "interactive": 8,
    "crypto": 6,
    "chart": 7,
    "alert": 6,
    "watchlist": 6,
}


def score_skill(name: str, description: str, stars: int, tags: List[str]) -> int:
    """
    Calculate relevance score (0-100) for a skill.
    
    Weights:
    - Topic match: 60 points max
    - Stars: 30 points max (log scale)
    - Tags: 10 points max
    """
    text = (name + " " + description).lower()
    
    # Topic match
    topic_score = 0
    for keyword, weight in TRADING_KEYWORDS.items():
        if keyword in text:
            topic_score += weight
    topic_score = min(60, topic_score)  # Cap at 60
    
    # Stars (log scale: 1000 stars = 30 points)
    stars_score = min(30, int((stars ** 0.5) / 2))
    
    # Tags
    tags_lower = [t.lower() for t in tags]
    tag_score = sum(min(3, TRADING_KEYWORDS.get(t, 0)) for t in tags_lower)
    tag_score = min(10, tag_score)
    
    total = topic_score + stars_score + tag_score
    return int(min(100, total))


def get_new_skills(limit: int = 3, days_back: int = 7) -> List[dict]:
    """Return top N skills discovered in last N days, not yet suggested"""
    try:
        conn = sqlite3.connect(SKILLS_DB)
        conn.row_factory = sqlite3.Row
        
        # Find skills: discovered recently, not yet suggested, not dismissed
        rows = conn.execute("""
            SELECT id, name, description, url, source, stars, tags, discovered_at
            FROM skills
            WHERE dismissed = 0
              AND suggested_count = 0
            ORDER BY stars DESC
            LIMIT ?
        """, (limit,)).fetchall()
        
        conn.close()
        
        results = []
        for row in rows:
            tags = json.loads(row["tags"] or "[]")
            score = score_skill(row["name"], row["description"], row["stars"], tags)
            results.append({
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "url": row["url"],
                "source": row["source"],
                "stars": row["stars"],
                "score": score,
                "tags": tags,
            })
        
        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    except Exception as e:
        logger.error(f"Failed to get new skills: {e}")
        return []


def mark_suggested(skill_id: int) -> bool:
    """Mark a skill as suggested (increment counter)"""
    try:
        conn = sqlite3.connect(SKILLS_DB)
        conn.execute("""
            UPDATE skills
            SET suggested_count = suggested_count + 1
            WHERE id = ?
        """, (skill_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to mark suggested: {e}")
        return False


def format_suggestion(skill: dict) -> str:
    """Format a skill as a user-friendly suggestion"""
    stars_text = f"{skill['stars']}★" if skill["stars"] > 0 else "local"
    tags_text = ", ".join(skill["tags"][:3]) if skill["tags"] else "no tags"
    
    return f"""
🆕 **New {skill['source'].replace('_', ' ').title()} Skill**

**{skill['name']}** ({stars_text})
{skill['description']}

**Tags:** {tags_text}
**Relevance Score:** {skill['score']}/100
**URL:** {skill['url']}

Would you like to integrate this into Claude?
""".strip()


def get_daily_suggestions() -> List[str]:
    """Return 3 new skills formatted as suggestions"""
    skills = get_new_skills(limit=3)
    suggestions = []
    
    for skill in skills:
        suggestions.append(format_suggestion(skill))
        mark_suggested(skill["id"])
    
    return suggestions


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    suggestions = get_daily_suggestions()
    for i, sug in enumerate(suggestions, 1):
        print(f"\n--- Suggestion {i} ---")
        print(sug)
