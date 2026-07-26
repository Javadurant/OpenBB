"""
use_quantedge.py
Place at: openbb_platform/use_quantedge.py
Run with: python use_quantedge.py

This is the correct way to use obsidian_exporter and notebooklm_exporter.
NEVER paste Python import statements directly into the terminal.
"""
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

from obsidian_exporter import ObsidianExporter
from notebooklm_exporter import NotebookLMExporter

VAULT_PATH = Path(
    os.getenv("OBSIDIAN_VAULT_PATH",
              str(Path.home() / "Documents" / "QuantEdge-Vault"))
)


def export_to_obsidian(symbol: str, analysis_result: Dict[str, Any]) -> None:
    exporter = ObsidianExporter(vault_path=VAULT_PATH)
    path = exporter.export_elliott_wave(symbol, analysis_result)
    print(f"Obsidian note: {path}")


def export_to_notebooklm(analyses: List[Dict[str, Any]]) -> None:
    exporter = NotebookLMExporter()
    path = exporter.export_weekly_digest(analyses)
    print(f"NotebookLM file: {path.resolve()}")
    print(f"Upload to: https://notebooklm.google.com/notebook/4db7b013-1664-4c4b-8c78-fd6a2cec748e")


if __name__ == "__main__":
    print(f"Vault: {VAULT_PATH}")

    sample: List[Dict[str, Any]] = [
        {
            "type": "Elliott Wave", "symbol": "SPY",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "data": {"valid_structure": True, "retrace_ratio": 0.618,
                     "target_1618": 542.5, "w4_valid": True},
        },
    ]

    print("\n[1] Obsidian export...")
    export_to_obsidian("SPY", sample[0]["data"])

    print("\n[2] NotebookLM export...")
    export_to_notebooklm(sample)

    print("\nDone.")
