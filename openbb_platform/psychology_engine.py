"""
psychology_engine.py
====================
Layer 3 — Psychology System: LlamaIndex over trading book PDFs.
Council verdict: highest leverage item, build first.

Upgrades the psychology module from static quotes to dynamic retrieval
grounded in the actual indexed books (Mark Douglas, Elder, Van Tharp, etc.)

Place at: openbb_platform/psychology_engine.py

Usage:
    from psychology_engine import PsychologyEngine
    psych = PsychologyEngine()

    # Pre-trade ritual (3 questions before any trade)
    ritual = psych.pre_trade_ritual("AAPL", "Long", "Breakout above 52-week high")

    # Post-trade debrief
    debrief = psych.post_trade_debrief(
        ticker="AAPL", direction="Long",
        outcome="Loss", pnl_pct=-2.1,
        journal="I entered late, chased the breakout"
    )

    # Direct question to the book library
    answer = psych.ask_books("What does Mark Douglas say about dealing with a losing streak?")
"""


# ── Env vars MUST be set before any torch / HF import ────────────────────
import os as _os                                                          # <- FIXED: env vars before HF imports
_os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")               # <- FIXED: MPS → CPU fallback, prevents disk-write crash on Apple Silicon
_os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")                # <- FIXED: suppress tokenizer fork deadlock warning
_os.environ.setdefault("HF_HUB_VERBOSITY", "error")                     # <- FIXED: suppress "unauthenticated requests" HF Hub warning

# ── Silence noisy third-party loggers ────────────────────────────────────
import logging as _logging
for _lib in (
    "httpx", "httpcore",
    "sentence_transformers", "sentence_transformers.base.model",
    "huggingface_hub", "huggingface_hub.utils._http",
    "huggingface_hub.utils._headers",                                    # <- ADDED: source of unauthenticated warning
    "transformers", "llama_index", "llama_index.core",
):
    _logging.getLogger(_lib).setLevel(_logging.ERROR)                    # <- FIXED: WARNING → ERROR silences auth nag


import os
import logging
import streamlit as st                                                    # <- ADDED [Council Fix-1]: required for @st.cache_resource on _load_index()
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────────────────
_root = Path(__file__).parent
load_dotenv(_root / ".env")

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────
BOOKS_DIR    = _root / "trading_books"
INDEX_DIR    = _root / ".index_cache"
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'")
GROQ_KEY      = os.getenv("GROQ_API_KEY",      "").strip().strip('"').strip("'")

# ── LlamaIndex setup ──────────────────────────────────────────────────────
_query_engine = None  # lazy loaded


@st.cache_resource(show_spinner=False)                                   # <- FIXED [Council Fix-1]: cache index across ALL Streamlit sessions — loads once per server restart, not per click
def _load_index():                                                        # <- FIXED [Council Fix-1]: without this decorator, 14 PDFs were re-embedded every single Analyze click (primary 20-min culprit)
    """
    Load or build the LlamaIndex vector index over trading_books/.
    Cached in .index_cache/ so rebuild only happens when new PDFs are added.
    """
    global _query_engine
    if _query_engine is not None:
        return _query_engine

    try:
        from llama_index.core import (
            SimpleDirectoryReader,
            VectorStoreIndex,
            StorageContext,
            load_index_from_storage,
            Settings,
        )
        from llama_index.core.node_parser import SentenceSplitter
    except ImportError:
        logger.warning(
            "llama-index not installed. "
            "Run: pip install llama-index llama-index-llms-anthropic "
            "llama-index-embeddings-huggingface"
        )
        return None

    # ── Configure LLM ─────────────────────────────────────────────────────
    if ANTHROPIC_KEY:
        try:
            from llama_index.llms.anthropic import Anthropic
            Settings.llm = Anthropic(
                model="claude-sonnet-4-20250514",                         # <- FIXED: correct Anthropic API model string
                api_key=ANTHROPIC_KEY,
                max_tokens=1024,
            )
        except ImportError:
            pass

    # ── Embeddings (local, no cost) ────────────────────────────────────────
    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        Settings.embed_model = HuggingFaceEmbedding(
            model_name="BAAI/bge-small-en-v1.5"
        )
    except ImportError:
        logger.warning(
            "HuggingFace embeddings not available. "
            "Run: pip install llama-index-embeddings-huggingface sentence-transformers"
        )

    # ── Books directory ───────────────────────────────────────────────────
    BOOKS_DIR.mkdir(exist_ok=True)
    INDEX_DIR.mkdir(exist_ok=True)

    if not any(BOOKS_DIR.glob("*.pdf")) and not any(BOOKS_DIR.glob("*.txt")):
        logger.warning(
            "No books found in trading_books/. "
            "Add PDF files to " + str(BOOKS_DIR) + " and restart."
        )
        return None

    # ── Load or rebuild index ─────────────────────────────────────────────
    try:
        storage = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
        index   = load_index_from_storage(storage)
        logger.info("Loaded existing index from cache.")
    except Exception:
        logger.info("Building new index from books (first run takes a few minutes)...")
        docs = SimpleDirectoryReader(
            str(BOOKS_DIR),
            required_exts=[".pdf", ".txt", ".md"],
            recursive=True,
        ).load_data()
        splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)
        index    = VectorStoreIndex.from_documents(docs, transformations=[splitter])
        index.storage_context.persist(persist_dir=str(INDEX_DIR))
        logger.info("Index built and cached.")

    _query_engine = index.as_query_engine(similarity_top_k=4)
    return _query_engine


class PsychologyEngine:
    """
    Trading psychology system backed by LlamaIndex retrieval over book PDFs.
    Falls back to curated static quotes if books are not indexed.
    """

    # ── Static fallbacks (used when no books are indexed yet) ─────────────
    _STATIC_EMOTIONAL = [
        "Are you entering this trade because it matches your plan, or because you're "
        "afraid of missing the move? (Douglas — Trading in the Zone)",
        "What is your emotional state right now? Calm and present, or anxious and reactive? "
        "Only trade when you're in the first state. (Elder — Trading for a Living)",
        "Is this trade an expression of your edge, or an expression of your need to be right? "
        "There is a profound difference. (Douglas — The Disciplined Trader)",
    ]

    _STATIC_PLAN = [
        "Does this trade fit your written plan exactly, or are you making an exception? "
        "Exceptions are how discipline erodes. (Elder)",
        "What is the specific setup you are trading? Can you name it in one sentence? "
        "If you cannot name it, you are not trading a system. (Van Tharp)",
        "Would you take this trade if you had just had five consecutive losses? "
        "If the answer changes, your decision is emotional, not systematic. (Douglas)",
    ]

    _STATIC_EXIT = [
        "Where is your stop? If you cannot say the exact price before you enter, "
        "do not enter. (Van Tharp — Trade Your Way to Financial Freedom)",
        "What is your R-multiple target? The trade should offer at least 2R. "
        "If it doesn't, the risk-reward does not justify the trade. (Van Tharp)",
        "If this trade goes against you immediately, what will you do? "
        "Pre-decide now, while you are calm. Do not decide under pressure. (Elder)",
    ]

    def __init__(self) -> None:
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            self._engine = _load_index()
        return self._engine

    def ask_books(self, question: str) -> str:
        """
        Query the indexed book library directly.
        Returns a grounded answer citing content from the books.
        """
        engine = self._get_engine()
        if engine is None:
            return (
                "Book index not available. Add PDF files to trading_books/ "
                "and restart to enable dynamic retrieval."
            )
        try:
            response = engine.query(question)
            return str(response)
        except Exception as e:
            logger.error("Query engine error: " + str(e))
            return "Query error: " + str(e)

    def pre_trade_ritual(
        self,
        ticker: str,
        direction: str,
        setup_description: str,
    ) -> dict:
        """
        Generate 3 pre-trade ritual questions grounded in the book library.
        One emotional state question, one plan-match question, one exit question.

        Returns a dict with questions and a verdict.
        """
        engine = self._get_engine()

        if engine is not None:
            # Dynamic — grounded in actual book content
            q1 = self.ask_books(
                f"What question should a trader ask themselves about emotional state "
                f"before entering a {direction} trade on a {setup_description} setup? "
                f"Quote from Mark Douglas or Alexander Elder."
            )
            q2 = self.ask_books(
                f"What question should a trader ask themselves about whether the trade "
                f"matches their written plan? Give one specific question from Van Tharp "
                f"or Mark Douglas."
            )
            q3 = self.ask_books(
                f"What should a trader define about their exit before entering? "
                f"Quote Van Tharp on R-multiples or Elder on stops."
            )
        else:
            # Static fallback
            import random
            q1 = random.choice(self._STATIC_EMOTIONAL)
            q2 = random.choice(self._STATIC_PLAN)
            q3 = random.choice(self._STATIC_EXIT)

        return {
            "ticker":    ticker,
            "direction": direction,
            "setup":     setup_description,
            "questions": {
                "1_emotional_state": q1,
                "2_plan_match":      q2,
                "3_exit_defined":    q3,
            },
            "instruction": (
                "Answer all three questions honestly before proceeding. "
                "If any answer is 'no' or 'I'm not sure' — do not enter the trade."
            ),
        }

    def post_trade_debrief(
        self,
        ticker:     str,
        direction:  str,
        outcome:    str,   # "Win" or "Loss" or "Breakeven"
        pnl_pct:    float,
        journal:    str,   # user's free-text journal entry
        followed_plan: Optional[bool] = None,
    ) -> dict:
        """
        Analyse a trade journal entry against the Douglas/Elder framework.
        Identifies the psychological pattern at play, independent of P&L.
        """
        engine = self._get_engine()

        # Process quality: separate from P&L
        if followed_plan is True:
            process = "GOOD PROCESS"
        elif followed_plan is False:
            process = "POOR PROCESS"
        else:
            process = "UNKNOWN PROCESS"

        if engine is not None:
            analysis = self.ask_books(
                f"A trader wrote: '{journal}'. They took a {direction} trade on {ticker} "
                f"and it was a {outcome} ({pnl_pct:+.1f}%). "
                f"Using the frameworks of Mark Douglas and Alexander Elder, "
                f"what psychological pattern is at play here? "
                f"Be direct and specific. Name the pattern. Do not soften the feedback."
            )
        else:
            # Static analysis based on keywords
            journal_lower = journal.lower()
            if any(w in journal_lower for w in ["chased", "fomo", "late", "missed"]):
                pattern = "Fear of Missing Out (FOMO). Douglas: the market will always provide another opportunity. This trade was taken from fear of missing, not from edge. The setup was not yours — it was the market's."
            elif any(w in journal_lower for w in ["moved stop", "held", "hope", "maybe"]):
                pattern = "Stop adjustment / hope trading. Elder: once you move a stop, you have admitted you do not have a plan. Hope is not a risk management strategy."
            elif any(w in journal_lower for w in ["revenge", "made back", "after loss"]):
                pattern = "Revenge trading. Douglas: the market owes you nothing. Every trade is independent. Trading to recover losses is not trading — it is gambling with extra steps."
            elif any(w in journal_lower for w in ["too small", "should have sized", "under-sized"]):
                pattern = "Conviction mismatch. Van Tharp: if your position size does not match your conviction rating, your system is not systematic. Size the trade based on the setup quality, not on anxiety."
            else:
                pattern = "Debrief the specific decision at each stage: entry trigger, position size, stop placement, exit. Which of these four deviated from your written plan?"
            analysis = pattern

        # Rate the trade: good process / bad process, win or loss = 4 types
        process_note = ""
        if outcome == "Loss" and followed_plan:
            process_note = "This was a GOOD LOSS. Good process with bad outcome is expected in any probabilistic system. Do not change anything."
        elif outcome == "Win" and not followed_plan:
            process_note = "This was a BAD WIN. Bad process with good outcome is dangerous — it rewards the wrong behaviour. Review what you violated."
        elif outcome == "Win" and followed_plan:
            process_note = "Clean execution. This is the standard to repeat."
        elif outcome == "Loss" and not followed_plan:
            process_note = "This was a BAD LOSS. The loss AND the process were wrong. Double review required."

        return {
            "ticker":      ticker,
            "direction":   direction,
            "outcome":     outcome,
            "pnl_pct":     pnl_pct,
            "process":     process,
            "process_note": process_note,
            "psychological_analysis": analysis,
            "journal":     journal,
        }

    def morning_psychology_check(self) -> str:
        """
        One grounding question from the books for the start of the trading day.
        """
        engine = self._get_engine()
        if engine is not None:
            return self.ask_books(
                "Give me one short, powerful question from Mark Douglas or Alexander Elder "
                "that a trader should ask themselves before the market opens. "
                "One sentence. No preamble."
            )
        import random
        return random.choice([
            "What is your edge today, and how will you know when it is present? (Douglas)",
            "Are you trading to make money or to be right? They are different motivations. (Elder)",
            "If you have no setups today, are you prepared to do nothing? That is also a skill. (Van Tharp)",
        ])

    def rebuild_index(self) -> str:
        """Force a full rebuild of the book index."""
        global _query_engine
        _query_engine = None
        self._engine  = None
        import shutil
        if INDEX_DIR.exists():
            shutil.rmtree(INDEX_DIR)
        engine = self._get_engine()
        if engine:
            return "Index rebuilt successfully from " + str(BOOKS_DIR)
        return "Rebuild attempted but no books found in " + str(BOOKS_DIR)


# ── Streamlit UI component ─────────────────────────────────────────────────
def render_pre_trade_ritual_ui(ticker: str, direction: str, setup: str) -> bool:
    """
    Renders the pre-trade ritual in Streamlit.
    Returns True if user confirms all 3 questions, False otherwise.
    Must be imported inside a Streamlit page.
    """
    try:
        import streamlit as st
    except ImportError:
        return True

    psych    = PsychologyEngine()
    ritual   = psych.pre_trade_ritual(ticker, direction, setup)
    qs       = ritual["questions"]

    st.markdown("---")
    st.markdown("### 🧠 Pre-Trade Ritual")
    st.caption("Answer honestly. If any answer is No — do not enter.")

    ok1 = st.checkbox(qs["1_emotional_state"], key="ritual_q1")
    ok2 = st.checkbox(qs["2_plan_match"],      key="ritual_q2")
    ok3 = st.checkbox(qs["3_exit_defined"],    key="ritual_q3")

    all_ok = ok1 and ok2 and ok3

    if all_ok:
        st.success("✅ Ritual complete. You may proceed.")
    else:
        st.warning("⚠️ Complete all three before entering.")

    st.markdown("---")
    return all_ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = PsychologyEngine()

    print("\n=== Pre-Trade Ritual ===")
    ritual = engine.pre_trade_ritual("VOLV-B.ST", "Long", "VCP breakout above 200-day MA")
    for k, v in ritual["questions"].items():
        print(f"\n{k}:\n{v}")

    print("\n=== Morning Check ===")
    print(engine.morning_psychology_check())

    print("\n=== Post-Trade Debrief ===")
    debrief = engine.post_trade_debrief(
        ticker="VOLV-B.ST",
        direction="Long",
        outcome="Loss",
        pnl_pct=-2.3,
        journal="I chased the entry — the stock had already moved 3% and I bought anyway because I didn't want to miss it",
        followed_plan=False,
    )
    print("Pattern:", debrief["psychological_analysis"])
    print("Process note:", debrief["process_note"])
