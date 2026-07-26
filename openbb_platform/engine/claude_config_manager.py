"""
engine/claude_config_manager.py — Auto-integrate MCPs into Claude Desktop (Phase 4)

Reads ~/.claude/claude_desktop_config.json
Auto-adds new MCPs when user approves a suggestion
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("QuantEdge.ClaudeConfigManager")

CLAUDE_CONFIG = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"


def get_claude_config() -> Optional[Dict[str, Any]]:
    """Read current Claude Desktop configuration"""
    if not CLAUDE_CONFIG.exists():
        logger.error(f"Claude config not found: {CLAUDE_CONFIG}")
        return None
    
    try:
        return json.loads(CLAUDE_CONFIG.read_text())
    except Exception as e:
        logger.error(f"Failed to read Claude config: {e}")
        return None


def add_mcp_to_claude(
    name: str,
    command: str,
    args: Optional[list] = None,
    env: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Add a new MCP server to Claude Desktop configuration.
    
    Example:
      add_mcp_to_claude(
          name="alpaca-trading",
          command="python",
          args=["-m", "alpaca_mcp_server"],
          env={"ALPACA_KEY": "..."}
      )
    """
    config = get_claude_config()
    if config is None:
        return False
    
    # Ensure mcpServers exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}
    
    # Add the MCP
    config["mcpServers"][name] = {
        "command": command,
        "args": args or [],
        "env": env or {},
    }
    
    # Write back
    try:
        CLAUDE_CONFIG.write_text(json.dumps(config, indent=2))
        logger.info(f"Added MCP '{name}' to Claude config")
        return True
    except Exception as e:
        logger.error(f"Failed to write Claude config: {e}")
        return False


def list_installed_mcps() -> Dict[str, Dict[str, Any]]:
    """Return list of all MCPs registered in Claude Desktop"""
    config = get_claude_config()
    return config.get("mcpServers", {}) if config else {}


def is_mcp_installed(name: str) -> bool:
    """Check if an MCP is already installed"""
    mcps = list_installed_mcps()
    return name in mcps


def needs_claude_restart() -> bool:
    """Return True if Claude Desktop needs restart to load new MCPs"""
    # In production: check if any MCPs were added since last restart
    # For now, always return True if any unloaded MCPs
    return True


def suggest_mcp_integration(skill: dict) -> str:
    """
    Generate integration instructions for a skill.
    
    Returns markdown with steps to add the MCP to Claude.
    """
    return f"""
## Integrate '{skill['name']}' into Claude Desktop

### Manual Steps:
1. Open `~/.claude/claude_desktop_config.json`
2. Add to `mcpServers`:
```json
"{skill['name']}": {{
  "command": "python",
  "args": ["-m", "{skill['name']}_mcp"],
  "env": {{}}
}}
```
3. Save and restart Claude Desktop

### Or auto-integrate (future):
Once you approve this skill in chat, it will auto-integrate and Claude will restart automatically.
"""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcps = list_installed_mcps()
    print(f"Currently installed MCPs: {list(mcps.keys())}")
