# engine/mcp_server.py
# QuantEdge — MCP Server (Python-based, no npm)
# Six-Role Panel: DEAN · PAEZ · SELIVANOV · KARPATHY · NILSSON · GURPREET SINGH
#
# ARCHITECTURE (Council Verdict — Session 2026-05-14, Path A 4-1):
#   Python MCP server that exposes the FastAPI gateway endpoints as
#   tools that Claude Desktop and any MCP-compliant client can invoke.
#
#   This file contains ZERO new trading logic.
#   All execution logic lives in engine/execution/order_manager.py.
#   All HTTP routing lives in engine/alpaca_gateway.py.
#   This file only marshals MCP tool calls into HTTP requests.
#
# TOOLS EXPOSED:
#   qe_health           — Gateway liveness probe
#   qe_get_account      — Account summary (SIMULATED or Alpaca)
#   qe_get_positions    — Open positions
#   qe_place_order      — Execute paper / simulated / live order
#
# WHY PYTHON MCP (not npm):
#   npm install for @modelcontextprotocol/sdk-based packages crashes with
#   `Cannot read properties of null (reading 'matches')` on npm 11.12.1.
#   Python MCP SDK (mcp 1.27.0) is already installed and proven working
#   (Polygon/Massive Market Data MCP runs via Python on this system).
#
# WHY HTTP-TO-MCP BRIDGE (instead of direct order_manager import):
#   Decouples MCP layer from execution layer. If the FastAPI gateway is
#   restarted, redeployed, or replaced, this MCP server does not need
#   modification — it only knows the HTTP contract.
#
# SECURITY (Gurpreet Singh):
#   This server makes HTTP calls only to 127.0.0.1:8001 — local-only.
#   No external network exposure. No credentials handled at this layer.
#   All credential management remains in the FastAPI gateway.
#
# USAGE:
#   Direct (testing):
#     python -m engine.mcp_server
#   Claude Desktop registration:
#     Add to ~/Library/Application Support/Claude/claude_desktop_config.json
#     (see manifest setup step in upcoming Council router build)
#
# PREREQUISITES:
#   1. FastAPI gateway must be running on port 8001:
#      uvicorn engine.alpaca_gateway:app --host 127.0.0.1 --port 8001
#   2. Python MCP SDK installed: pip show mcp (confirmed v1.27.0)
#
# <- NEW [mcp_server]: Python MCP server bridging FastAPI gateway to Claude

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List

# -- Resolve project root --
_ROOT: str = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)  # <- NEW [mcp_server]: project root for imports

import requests
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger("QuantEdge.MCPServer")

# -- Module-level constants --
MCP_SERVER_NAME:    str   = "quantedge-trading"
MCP_SERVER_VERSION: str   = "1.0.0"
GATEWAY_BASE_URL:   str   = os.environ.get("QE_GATEWAY_URL", "http://127.0.0.1:8001")
HTTP_TIMEOUT:       float = 15.0
FLOAT_EPSILON:      float = 1e-10


# -- Tool implementations (HTTP bridges) --
def _http_get(endpoint: str) -> Dict[str, Any]:
    """
    Issues a GET to the FastAPI gateway. Returns parsed JSON dict.
    Errors are caught and returned as {"error": "..."} for MCP transport.
    """
    url = f"{GATEWAY_BASE_URL}{endpoint}"
    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT)
    except requests.exceptions.ConnectionError:
        return {"error": f"Gateway unreachable at {url}. "
                         f"Start it: uvicorn engine.alpaca_gateway:app --port 8001"}
    except requests.exceptions.Timeout:
        return {"error": f"Gateway timeout after {HTTP_TIMEOUT}s at {url}"}
    except Exception as exc:
        logger.error("HTTP GET error for %s: %s", url, exc)
        return {"error": f"HTTP error: {exc}"}

    try:
        return resp.json()
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid JSON from gateway: {exc}", "status": resp.status_code}


def _http_post(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Issues a POST with JSON body. Returns parsed JSON dict.
    """
    url = f"{GATEWAY_BASE_URL}{endpoint}"
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=HTTP_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        return {"error": f"Gateway unreachable at {url}"}
    except requests.exceptions.Timeout:
        return {"error": f"Gateway timeout after {HTTP_TIMEOUT}s"}
    except Exception as exc:
        logger.error("HTTP POST error for %s: %s", url, exc)
        return {"error": f"HTTP error: {exc}"}

    try:
        return resp.json()
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid JSON: {exc}", "status": resp.status_code}


# -- MCP server instance --
server: Server = Server(MCP_SERVER_NAME)


# -- Tool: list_tools handler --
@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    """
    Returns the full list of tools this server provides to MCP clients.
    Schema follows JSON Schema draft-07 conventions per MCP specification.
    """
    return [
        Tool(
            name="qe_health",
            description=(
                "Check QuantEdge FastAPI gateway liveness and broker mode. "
                "Returns: status, version, broker_mode (SIMULATED/ALPACA_PAPER/ALPACA_LIVE), "
                "exec_mode, key presence flags, simulated capital amount."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="qe_get_account",
            description=(
                "Fetch trading account summary: equity, buying power, cash. "
                "In SIMULATED mode (default), returns synthetic snapshot from QE_CAPITAL_USD. "
                "In ALPACA_* modes, returns live Alpaca account data."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="qe_get_positions",
            description=(
                "Fetch list of currently open positions with unrealized P&L per position. "
                "In SIMULATED mode, returns empty list (positions tracked client-side). "
                "In ALPACA_* modes, returns live Alpaca positions."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="qe_place_order",
            description=(
                "Execute a paper, simulated, or live order through the QuantEdge order manager. "
                "Position sizing is computed using the 2% risk rule with a 10% max position cap. "
                "Swedish OMX tickers (.ST suffix) always route to SIMULATED mode. "
                "US tickers route to the configured broker (SIMULATED, ALPACA_PAPER, or ALPACA_LIVE). "
                "Returns: order result (success, order_id, qty, price, total_usd/sek, broker) "
                "plus position sizing details (shares, cost, risk amount, FX rate, capital used %)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Equity symbol. US: AAPL, TSLA, MSFT. OMX: ERIC-B.ST, VOLV-B.ST.",
                        "minLength": 1,
                        "maxLength": 20,
                    },
                    "side": {
                        "type": "string",
                        "description": "Order direction.",
                        "enum": ["buy", "sell"],
                    },
                    "entry_price": {
                        "type": "number",
                        "description": "Entry price in the ticker's native currency. Must be > 0.",
                        "exclusiveMinimum": 0,
                    },
                    "stop_loss": {
                        "type": "number",
                        "description": (
                            "Stop-loss price for risk-based position sizing. "
                            "Must be > 0 and differ from entry_price (epsilon = 1e-10)."
                        ),
                        "exclusiveMinimum": 0,
                    },
                },
                "required": ["ticker", "side", "entry_price", "stop_loss"],
            },
        ),
    ]


# -- Tool: call_tool handler --
@server.call_tool()
async def handle_call_tool(
    name: str, arguments: Dict[str, Any]
) -> List[TextContent]:
    """
    Routes MCP tool calls to the appropriate HTTP bridge.
    Every response is returned as a single TextContent with JSON payload.
    """
    logger.info("Tool call: %s args=%s", name, arguments)

    if name == "qe_health":
        result = _http_get("/health")

    elif name == "qe_get_account":
        result = _http_get("/alpaca/account")

    elif name == "qe_get_positions":
        result = _http_get("/alpaca/positions")

    elif name == "qe_place_order":
        # Validate required fields before HTTP call
        required = ("ticker", "side", "entry_price", "stop_loss")
        missing = [k for k in required if k not in arguments]
        if missing:
            result = {"error": f"Missing required fields: {', '.join(missing)}"}
        else:
            ticker  = str(arguments["ticker"]).strip().upper()
            side    = str(arguments["side"]).strip().lower()
            entry_p = float(arguments["entry_price"])
            stop_l  = float(arguments["stop_loss"])

            # Float safety — Karpathy mandate
            if abs(entry_p - stop_l) < FLOAT_EPSILON:
                result = {
                    "error": (
                        f"entry_price ({entry_p}) and stop_loss ({stop_l}) "
                        "are equal or within float epsilon — risk sizing requires a gap."
                    )
                }
            elif side not in ("buy", "sell"):
                result = {"error": f"Invalid side '{side}'. Must be 'buy' or 'sell'."}
            else:
                result = _http_post(
                    "/alpaca/order",
                    {
                        "ticker": ticker,
                        "side": side,
                        "entry_price": entry_p,
                        "stop_loss": stop_l,
                    },
                )

    else:
        result = {"error": f"Unknown tool: '{name}'. "
                           f"Available: qe_health, qe_get_account, qe_get_positions, qe_place_order"}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# -- Entry point --
async def _main() -> None:
    """
    Runs the MCP server over stdio transport.
    Claude Desktop and other MCP clients connect via stdin/stdout.
    """
    logger.info(
        "QuantEdge MCP Server v%s starting. gateway=%s",
        MCP_SERVER_VERSION, GATEWAY_BASE_URL,
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Synchronous entry point for module execution."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,  # stdout reserved for MCP JSON-RPC traffic
    )
    asyncio.run(_main())


if __name__ == "__main__":
    main()
