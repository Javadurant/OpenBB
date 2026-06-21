# engine/copilot/engine.py
import os
import json
import logging
import asyncio
from typing import AsyncGenerator
from dotenv import load_dotenv # ← ADDED: Load environment variables from .env

# SOFT-FAIL DEPENDENCY CHECK
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ModuleNotFoundError:
    OPENAI_AVAILABLE = False

# 1. GATHER CONFIGURATION
load_dotenv() # ← ADDED: Explicitly load variables before reading key
api_key = os.getenv("OPENAI_API_KEY")

# 2. INITIALIZE CLIENT SAFELY (Prevent crash at import time)
client = None
if OPENAI_AVAILABLE and api_key:
    try:
        # Failsafe: only instantiate if key is present and looks valid
        if api_key.startswith("sk-"):
            client = AsyncOpenAI(api_key=api_key)
    except Exception as e:
        logging.error(f"Failed to initialize OpenAI client: {e}")
        client = None

SYSTEM_PROMPT = """
You are the OpenBB Alpha Copilot, a Senior Quantitative Strategist and AI Research Assistant.
Your goal is to provide objective, data-driven reasoning based on the provided technical analysis, 
ML predictions, and institutional evidence.

CORE PROTOCOLS:
1. DO NOT provide financial advice or "buy/sell" signals. 
2. Use the 'action_plan' to discuss geometric patterns (Harmonics, Elliott Waves).
3. Use 'evidence' to explain the confluence of Trend, Momentum, and Structure.
4. If ML 'prediction' and 'evidence' diverge, highlight the discrepancy as a risk.
5. Reference specific price levels (PRZ, Fibonacci) provided in the context.
6. Keep responses professional, concise, and scannable (use Markdown).
"""

async def get_copilot_response(
    query: str, 
    context: dict, 
    history: list
) -> AsyncGenerator[str, None]:
    """
    Generates a streaming response from the AI Copilot based on real-time market quant data.
    """
    if not OPENAI_AVAILABLE:
        yield "⚠️ **Dependency Error:** The `openai` Python package is not installed."
        return

    if not client:
        yield "⚠️ **Configuration Error:** `OPENAI_API_KEY` is missing or invalid in environment variables."
        return

    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in history[-5:]:
            messages.append(msg)
            
        market_context_str = json.dumps(context, indent=2)
        messages.append({
            "role": "user", 
            "content": f"MARKET DATA CONTEXT:\n{market_context_str}\n\nUSER QUERY: {query}"
        })

        stream = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            stream=True,
            temperature=0.2
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except Exception as e:
        logging.error(f"Copilot Engine Error: {str(e)}")
        yield f"⚠️ **Copilot Error:** {str(e)}"