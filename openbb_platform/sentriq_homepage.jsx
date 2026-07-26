import React, { useState, useMemo, useEffect, useRef, useCallback } from "react";
import {
  Search,
  Brain,
  BookOpen,
  Trophy,
  TrendingUp,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  X,
  Sparkles,
  Activity,
  Lock,
  Building2,
} from "lucide-react";

/* ──────────────────────────────────────────────────────────────────────
   SENTRIQ — Transparent Signal Hub
   Marketing landing surface (not the trading workspace).
   Conforms to Kinetic Obsidian: dark obsidian base, electric cyan
   accent, Inter for UI, JetBrains Mono for numerical data,
   glassmorphism reserved for the Vault-tier (Mastermind) card.
   ────────────────────────────────────────────────────────────────────── */

/* ─── DATA LAYER ─────────────────────────────────────────────────────
   Shape mirrors what an OpenBB equity.search response normalizes to
   ({ symbol, name, exchange }) so this component is API-ready: swap
   TICKER_INDEX for a fetched array and the search bar continues to work.
   ────────────────────────────────────────────────────────────────── */
const TICKER_INDEX = [
  // US large caps
  { ticker: "AAPL", name: "Apple Inc.", exchange: "NASDAQ" },
  { ticker: "NVDA", name: "NVIDIA Corporation", exchange: "NASDAQ" },
  { ticker: "MSFT", name: "Microsoft Corporation", exchange: "NASDAQ" },
  { ticker: "GOOGL", name: "Alphabet Inc.", exchange: "NASDAQ" },
  { ticker: "META", name: "Meta Platforms, Inc.", exchange: "NASDAQ" },
  { ticker: "AMZN", name: "Amazon.com, Inc.", exchange: "NASDAQ" },
  { ticker: "TSLA", name: "Tesla, Inc.", exchange: "NASDAQ" },
  { ticker: "BRK.B", name: "Berkshire Hathaway Inc.", exchange: "NYSE" },
  { ticker: "JPM", name: "JPMorgan Chase & Co.", exchange: "NYSE" },
  { ticker: "V", name: "Visa Inc.", exchange: "NYSE" },
  { ticker: "AMD", name: "Advanced Micro Devices, Inc.", exchange: "NASDAQ" },
  { ticker: "NFLX", name: "Netflix, Inc.", exchange: "NASDAQ" },
  // OMX Stockholm — Javadurant's home market
  { ticker: "VOLV-B.ST", name: "Volvo AB", exchange: "OMX" },
  { ticker: "ERIC-B.ST", name: "Telefonaktiebolaget LM Ericsson", exchange: "OMX" },
  { ticker: "HM-B.ST", name: "H & M Hennes & Mauritz AB", exchange: "OMX" },
  { ticker: "INVE-B.ST", name: "Investor AB", exchange: "OMX" },
  { ticker: "ATCO-A.ST", name: "Atlas Copco AB", exchange: "OMX" },
  { ticker: "SAND.ST", name: "Sandvik AB", exchange: "OMX" },
  { ticker: "SEB-A.ST", name: "Skandinaviska Enskilda Banken AB", exchange: "OMX" },
  { ticker: "EVO.ST", name: "Evolution AB", exchange: "OMX" },
];

/* ─── CARD SPECS ─────────────────────────────────────────────────────
   Typed array. Each entry is one logical "story panel" in the homepage
   stack. The `apiSlot` field marks which live data source will plug in
   when the OpenBB layer is wired (e.g. signal-of-the-day, top-mover).
   ────────────────────────────────────────────────────────────────── */
const CARDS = [
  {
    id: "logic",
    eyebrow: "01 / LOGIC",
    title: "Pattern recognition the eye misses",
    subtitle: "Bullish Butterfly — five-point harmonic structure",
    body:
      "We screen continuously for XABCD harmonic completions with strict Fibonacci validation. Every signal carries its own invalidation level — no pattern, no trade.",
    accent: "cyan",
    icon: Activity,
    visual: "butterfly",
    apiSlot: "signal_of_the_day",
  },
  {
    id: "wisdom",
    eyebrow: "02 / WISDOM",
    title: "Methods that survived four decades of regime change",
    subtitle: "The canonical reading list, indexed against every signal",
    body:
      "Markets evolve, principles don't. SENTRIQ tags every alert with the discipline it depends on, so you trade the playbook — not the impulse.",
    accent: "amber",
    icon: BookOpen,
    visual: "books",
    apiSlot: null,
  },
  {
    id: "emotion",
    eyebrow: "03 / EMOTION",
    title: "The moment the math becomes money",
    subtitle: "Closed positions. Realized P&L. The thesis pays.",
    body:
      "Every winning exit is a vote for staying disciplined. SENTRIQ logs the why next to the what, so the next trade isn't built on a feeling.",
    accent: "emerald",
    icon: Trophy,
    visual: "celebration",
    apiSlot: "recent_wins_feed",
  },
  {
    id: "vision",
    eyebrow: "04 / VISION",
    title: "Compounding edge beats moonshots",
    subtitle: "1% monthly edge, ten years, vs. one big swing",
    body:
      "The trader who edges the market by a measurable, repeatable amount outperforms the trader hunting moonshots. SENTRIQ is built for that arithmetic.",
    accent: "sky",
    icon: TrendingUp,
    visual: "growth",
    apiSlot: "portfolio_equity_curve",
  },
  {
    id: "mastermind",
    eyebrow: "05 / CLAUDE'S CHOICE",
    title: "The psychological edge layer",
    subtitle: "Mastermind — for when the chart looks easy and the click is hard",
    body:
      "Signals are easy. Acting on them under pressure is the entire game. Mastermind flags revenge trades, FOMO entries, and conviction drift before you click.",
    accent: "violet",
    icon: Brain,
    visual: "neural",
    apiSlot: "psych_state_check",
    isVault: true,
  },
];

/* ─── ACCENT TOKEN MAP ──────────────────────────────────────────────
   Per-card color tokens. Kept here (not inlined) so theming is
   centralized and Tailwind's JIT compiler keeps every class.
   ────────────────────────────────────────────────────────────────── */
const ACCENT = {
  cyan: {
    text: "text-cyan-300",
    glow: "shadow-[0_0_60px_-10px_rgba(34,211,238,0.45)]",
    border: "border-cyan-400/30",
    chip: "bg-cyan-400/10 text-cyan-200 border-cyan-400/30",
    line: "stroke-cyan-300",
    fill: "fill-cyan-300",
    rgb: "34,211,238",
  },
  amber: {
    text: "text-amber-300",
    glow: "shadow-[0_0_60px_-10px_rgba(251,191,36,0.4)]",
    border: "border-amber-400/30",
    chip: "bg-amber-400/10 text-amber-200 border-amber-400/30",
    line: "stroke-amber-300",
    fill: "fill-amber-300",
    rgb: "251,191,36",
  },
  emerald: {
    text: "text-emerald-300",
    glow: "shadow-[0_0_60px_-10px_rgba(52,211,153,0.4)]",
    border: "border-emerald-400/30",
    chip: "bg-emerald-400/10 text-emerald-200 border-emerald-400/30",
    line: "stroke-emerald-300",
    fill: "fill-emerald-300",
    rgb: "52,211,153",
  },
  sky: {
    text: "text-sky-300",
    glow: "shadow-[0_0_60px_-10px_rgba(56,189,248,0.4)]",
    border: "border-sky-400/30",
    chip: "bg-sky-400/10 text-sky-200 border-sky-400/30",
    line: "stroke-sky-300",
    fill: "fill-sky-300",
    rgb: "56,189,248",
  },
  violet: {
    text: "text-violet-300",
    glow: "shadow-[0_0_80px_-8px_rgba(167,139,250,0.55)]",
    border: "border-violet-400/40",
    chip: "bg-violet-400/10 text-violet-200 border-violet-400/30",
    line: "stroke-violet-300",
    fill: "fill-violet-300",
    rgb: "167,139,250",
  },
};

/* ─── VISUALS — inline SVG, no external assets ──────────────────────
   Every visual is an original SVG. Book objects use real titles
   (titles are not copyrightable; cover art is — we render type only).
   No photographs of identifiable people.
   ────────────────────────────────────────────────────────────────── */

function ButterflyHarmonicVisual({ accent }) {
  // Domain note: the structure shown is a Bullish Butterfly — five-point
  // XABCD pattern. The annotation calls out the D-leg as a 1.27–1.618
  // extension of XA, which is the canonical Carney definition of the
  // Butterfly's PRZ. No invented ratios.
  const a = ACCENT[accent];
  return (
    <svg viewBox="0 0 480 280" className="w-full h-full" aria-hidden="true">
      <defs>
        <linearGradient id="bf-grad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={`rgba(${a.rgb},0.25)`} />
          <stop offset="100%" stopColor={`rgba(${a.rgb},0)`} />
        </linearGradient>
      </defs>
      {/* grid */}
      <g stroke="rgba(255,255,255,0.04)" strokeWidth="1">
        {[0, 1, 2, 3, 4].map((i) => (
          <line key={`h${i}`} x1="0" x2="480" y1={40 + i * 50} y2={40 + i * 50} />
        ))}
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <line key={`v${i}`} y1="20" y2="260" x1={60 + i * 70} x2={60 + i * 70} />
        ))}
      </g>
      {/* XABCD pattern path — bullish butterfly geometry */}
      <polyline
        points="40,80 140,200 220,110 320,180 420,240"
        className={a.line}
        strokeWidth="2.25"
        fill="none"
      />
      <polyline
        points="40,80 140,200 220,110 320,180 420,240 420,260 40,260"
        fill="url(#bf-grad)"
        stroke="none"
      />
      {/* Pivot points */}
      {[
        { x: 40, y: 80, label: "X" },
        { x: 140, y: 200, label: "A" },
        { x: 220, y: 110, label: "B" },
        { x: 320, y: 180, label: "C" },
        { x: 420, y: 240, label: "D" },
      ].map((p) => (
        <g key={p.label}>
          <circle cx={p.x} cy={p.y} r="5" className={a.fill} />
          <circle cx={p.x} cy={p.y} r="10" fill="none" className={a.line} strokeWidth="1" opacity="0.4" />
          <text
            x={p.x}
            y={p.y - 14}
            textAnchor="middle"
            fontSize="11"
            fontWeight="600"
            fill="#e4e4e7"
            fontFamily="ui-monospace, 'JetBrains Mono', monospace"
          >
            {p.label}
          </text>
        </g>
      ))}
      {/* PRZ annotation on D-leg — sourced from Carney's harmonic reference */}
      <line
        x1="440"
        x2="440"
        y1="80"
        y2="240"
        stroke="rgba(255,255,255,0.18)"
        strokeWidth="1"
        strokeDasharray="3 3"
      />
      <text
        x="448"
        y="160"
        fontSize="10"
        fill="#a1a1aa"
        fontFamily="ui-monospace, 'JetBrains Mono', monospace"
      >
        D-leg
      </text>
      <text
        x="448"
        y="174"
        fontSize="10"
        fill="#a1a1aa"
        fontFamily="ui-monospace, 'JetBrains Mono', monospace"
      >
        1.27–1.618
      </text>
      <text
        x="448"
        y="188"
        fontSize="10"
        fill="#a1a1aa"
        fontFamily="ui-monospace, 'JetBrains Mono', monospace"
      >
        of XA
      </text>
    </svg>
  );
}

function BookStackVisual({ accent }) {
  // Real titles set in type. No reproduction of cover artwork.
  const a = ACCENT[accent];
  const books = [
    { title: "The Disciplined Trader", author: "Mark Douglas", spine: "#3a2c1a", ink: "#fde68a" },
    { title: "Reminiscences of a Stock Operator", author: "Edwin Lefèvre", spine: "#1f2937", ink: "#e5e7eb" },
    { title: "Market Wizards", author: "Jack D. Schwager", spine: "#3f1d2c", ink: "#fecaca" },
  ];
  return (
    <svg viewBox="0 0 480 280" className="w-full h-full" aria-hidden="true">
      <defs>
        <linearGradient id="shelf" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="rgba(255,255,255,0.04)" />
          <stop offset="100%" stopColor="rgba(255,255,255,0)" />
        </linearGradient>
      </defs>
      {/* shelf */}
      <rect x="20" y="232" width="440" height="6" fill="rgba(255,255,255,0.08)" />
      <rect x="20" y="238" width="440" height="2" fill="rgba(255,255,255,0.16)" />
      <rect x="20" y="40" width="440" height="192" fill="url(#shelf)" />
      {books.map((b, i) => {
        const x = 70 + i * 118;
        const tilt = i === 1 ? -2 : 0;
        return (
          <g key={b.title} transform={`translate(${x},78) rotate(${tilt} 50 80)`}>
            {/* book body */}
            <rect width="100" height="154" rx="3" fill={b.spine} />
            {/* spine highlight */}
            <rect width="6" height="154" rx="2" fill="rgba(255,255,255,0.12)" />
            <rect x="94" width="6" height="154" rx="2" fill="rgba(0,0,0,0.35)" />
            {/* accent band */}
            <rect y="20" width="100" height="3" className={a.fill} opacity="0.7" />
            <rect y="131" width="100" height="3" className={a.fill} opacity="0.7" />
            {/* title typeset rotated */}
            <g transform="translate(50,140) rotate(-90)">
              <text
                x="0"
                y="0"
                textAnchor="start"
                fontSize="11"
                fontWeight="700"
                fill={b.ink}
                fontFamily="'Inter', system-ui, sans-serif"
                letterSpacing="0.5"
              >
                {b.title.toUpperCase()}
              </text>
              <text
                x="0"
                y="14"
                textAnchor="start"
                fontSize="8"
                fill={b.ink}
                opacity="0.65"
                fontFamily="'Inter', system-ui, sans-serif"
              >
                {b.author}
              </text>
            </g>
          </g>
        );
      })}
      {/* pull-quote */}
      <g>
        <text
          x="240"
          y="44"
          textAnchor="middle"
          fontSize="11"
          fill="#a1a1aa"
          fontFamily="'Inter', system-ui, sans-serif"
          fontStyle="italic"
        >
          "The hard work in trading comes in the preparation."
        </text>
      </g>
    </svg>
  );
}

function CelebrationVisual({ accent }) {
  // Abstract win motif — rising P&L curve with confetti shards.
  // No human figures, no stock photography.
  const a = ACCENT[accent];
  return (
    <svg viewBox="0 0 480 280" className="w-full h-full" aria-hidden="true">
      <defs>
        <linearGradient id="win-grad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={`rgba(${a.rgb},0.32)`} />
          <stop offset="100%" stopColor={`rgba(${a.rgb},0)`} />
        </linearGradient>
      </defs>
      {/* grid */}
      <g stroke="rgba(255,255,255,0.04)" strokeWidth="1">
        {[0, 1, 2, 3, 4].map((i) => (
          <line key={i} x1="20" x2="460" y1={50 + i * 45} y2={50 + i * 45} />
        ))}
      </g>
      {/* P&L curve */}
      <path
        d="M30,230 L80,225 L130,210 L180,205 L230,180 L280,160 L330,120 L380,90 L430,50"
        className={a.line}
        strokeWidth="2.5"
        fill="none"
      />
      <path
        d="M30,230 L80,225 L130,210 L180,205 L230,180 L280,160 L330,120 L380,90 L430,50 L430,250 L30,250 Z"
        fill="url(#win-grad)"
        stroke="none"
      />
      {/* end marker */}
      <circle cx="430" cy="50" r="5" className={a.fill} />
      <circle cx="430" cy="50" r="14" fill="none" className={a.line} strokeWidth="1" opacity="0.4">
        <animate attributeName="r" from="6" to="22" dur="2s" repeatCount="indefinite" />
        <animate attributeName="opacity" from="0.6" to="0" dur="2s" repeatCount="indefinite" />
      </circle>
      {/* confetti shards */}
      {[
        { x: 60, y: 60, r: 18, w: 10, h: 3, c: a.fill },
        { x: 110, y: 90, r: -22, w: 12, h: 3, c: "fill-zinc-300" },
        { x: 170, y: 70, r: 35, w: 8, h: 3, c: a.fill },
        { x: 240, y: 50, r: -8, w: 14, h: 3, c: "fill-zinc-400" },
        { x: 310, y: 80, r: 12, w: 10, h: 3, c: a.fill },
        { x: 360, y: 40, r: -28, w: 12, h: 3, c: "fill-zinc-300" },
        { x: 400, y: 110, r: 50, w: 8, h: 3, c: a.fill },
      ].map((c, i) => (
        <rect
          key={i}
          x={c.x}
          y={c.y}
          width={c.w}
          height={c.h}
          className={c.c}
          transform={`rotate(${c.r} ${c.x + c.w / 2} ${c.y + c.h / 2})`}
          opacity="0.8"
        />
      ))}
      {/* P&L label */}
      <g>
        <rect x="350" y="20" width="110" height="22" rx="11" fill="rgba(0,0,0,0.4)" stroke={`rgba(${a.rgb},0.4)`} />
        <text
          x="405"
          y="35"
          textAnchor="middle"
          fontSize="11"
          fontWeight="600"
          className={a.text}
          fontFamily="ui-monospace, 'JetBrains Mono', monospace"
        >
          +24.6% YTD
        </text>
      </g>
    </svg>
  );
}

function GrowthCurveVisual({ accent }) {
  // Vision card — mild greens/blues per brief. Smooth equity curve
  // with milestone markers. Numbers are illustrative; flagged as such
  // in the legend so no live-data claim is made.
  const a = ACCENT[accent];
  const points = [
    { x: 40, y: 220, label: "Y1" },
    { x: 110, y: 200, label: "Y2" },
    { x: 180, y: 175, label: "Y3" },
    { x: 250, y: 145, label: "Y4" },
    { x: 320, y: 110, label: "Y5" },
    { x: 390, y: 65, label: "Y6" },
  ];
  return (
    <svg viewBox="0 0 480 280" className="w-full h-full" aria-hidden="true">
      <defs>
        <linearGradient id="vision-grad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={`rgba(${a.rgb},0.32)`} />
          <stop offset="60%" stopColor={`rgba(${a.rgb},0.08)`} />
          <stop offset="100%" stopColor={`rgba(${a.rgb},0)`} />
        </linearGradient>
        <linearGradient id="vision-stroke" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor={`rgba(${a.rgb},0.5)`} />
          <stop offset="100%" stopColor={`rgba(${a.rgb},1)`} />
        </linearGradient>
      </defs>
      {/* baseline */}
      <line x1="30" x2="450" y1="240" y2="240" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
      {/* gridlines */}
      <g stroke="rgba(255,255,255,0.04)" strokeDasharray="2 4">
        {[60, 100, 140, 180, 220].map((y) => (
          <line key={y} x1="30" x2="450" y1={y} y2={y} />
        ))}
      </g>
      {/* fill area */}
      <path
        d={`M${points[0].x},240 ${points
          .map((p) => `L${p.x},${p.y}`)
          .join(" ")} L${points[points.length - 1].x},240 Z`}
        fill="url(#vision-grad)"
      />
      {/* curve */}
      <path
        d={`M${points[0].x},${points[0].y} ${points
          .slice(1)
          .map((p) => `L${p.x},${p.y}`)
          .join(" ")}`}
        stroke="url(#vision-stroke)"
        strokeWidth="2.5"
        fill="none"
      />
      {/* milestone dots */}
      {points.map((p) => (
        <g key={p.label}>
          <circle cx={p.x} cy={p.y} r="4" className={a.fill} />
          <text
            x={p.x}
            y="258"
            textAnchor="middle"
            fontSize="9"
            fill="#71717a"
            fontFamily="ui-monospace, 'JetBrains Mono', monospace"
          >
            {p.label}
          </text>
        </g>
      ))}
      {/* annotation */}
      <g>
        <text
          x="40"
          y="40"
          fontSize="11"
          fill="#a1a1aa"
          fontFamily="'Inter', system-ui, sans-serif"
        >
          Compounding the edge
        </text>
        <text
          x="40"
          y="58"
          fontSize="22"
          fontWeight="700"
          fill="#fafafa"
          fontFamily="ui-monospace, 'JetBrains Mono', monospace"
        >
          1.0% → 12.7% / yr
        </text>
        <text
          x="40"
          y="72"
          fontSize="9"
          fill="#52525b"
          fontFamily="'Inter', system-ui, sans-serif"
        >
          illustrative — for reference only
        </text>
      </g>
    </svg>
  );
}

function NeuralVisual({ accent }) {
  // Mastermind — psychological edge layer. Synapse / decision-graph motif.
  const a = ACCENT[accent];
  const nodes = [
    { x: 90, y: 90, r: 8, primary: true },
    { x: 200, y: 60, r: 6 },
    { x: 200, y: 130, r: 7 },
    { x: 320, y: 80, r: 6 },
    { x: 320, y: 200, r: 8, primary: true },
    { x: 420, y: 130, r: 9, primary: true },
    { x: 100, y: 210, r: 6 },
    { x: 240, y: 220, r: 5 },
  ];
  const edges = [
    [0, 1], [0, 2], [1, 3], [2, 3], [2, 4], [3, 5],
    [4, 5], [0, 6], [6, 7], [7, 4], [2, 7],
  ];
  return (
    <svg viewBox="0 0 480 280" className="w-full h-full" aria-hidden="true">
      <defs>
        <radialGradient id="brain-glow" cx="50%" cy="50%" r="60%">
          <stop offset="0%" stopColor={`rgba(${a.rgb},0.18)`} />
          <stop offset="100%" stopColor={`rgba(${a.rgb},0)`} />
        </radialGradient>
      </defs>
      <rect width="480" height="280" fill="url(#brain-glow)" />
      {/* edges */}
      {edges.map(([i, j], idx) => (
        <line
          key={idx}
          x1={nodes[i].x}
          y1={nodes[i].y}
          x2={nodes[j].x}
          y2={nodes[j].y}
          stroke={`rgba(${a.rgb},0.35)`}
          strokeWidth="1"
        />
      ))}
      {/* pulsing edge to indicate signal flow */}
      <line
        x1={nodes[0].x}
        y1={nodes[0].y}
        x2={nodes[5].x}
        y2={nodes[5].y}
        stroke={`rgba(${a.rgb},0.9)`}
        strokeWidth="1.5"
        strokeDasharray="4 6"
      >
        <animate attributeName="stroke-dashoffset" from="0" to="-20" dur="1.5s" repeatCount="indefinite" />
      </line>
      {/* nodes */}
      {nodes.map((n, idx) => (
        <g key={idx}>
          {n.primary && (
            <circle cx={n.x} cy={n.y} r={n.r + 6} fill="none" className={a.line} strokeWidth="1" opacity="0.4">
              <animate attributeName="r" from={n.r + 4} to={n.r + 14} dur="2.4s" repeatCount="indefinite" />
              <animate attributeName="opacity" from="0.5" to="0" dur="2.4s" repeatCount="indefinite" />
            </circle>
          )}
          <circle cx={n.x} cy={n.y} r={n.r} className={a.fill} />
          <circle cx={n.x} cy={n.y} r={n.r} fill="none" stroke="rgba(255,255,255,0.2)" />
        </g>
      ))}
      {/* state chip */}
      <g>
        <rect
          x="30"
          y="34"
          width="140"
          height="26"
          rx="13"
          fill="rgba(0,0,0,0.55)"
          stroke={`rgba(${a.rgb},0.4)`}
        />
        <circle cx="48" cy="47" r="4" className={a.fill}>
          <animate attributeName="opacity" from="1" to="0.3" dur="1.2s" repeatCount="indefinite" />
        </circle>
        <text
          x="60"
          y="51"
          fontSize="11"
          fontWeight="600"
          className={a.text}
          fontFamily="ui-monospace, 'JetBrains Mono', monospace"
        >
          STATE: COMPOSED
        </text>
      </g>
      <g>
        <rect
          x="310"
          y="34"
          width="140"
          height="26"
          rx="13"
          fill="rgba(0,0,0,0.55)"
          stroke="rgba(255,255,255,0.12)"
        />
        <text
          x="380"
          y="51"
          textAnchor="middle"
          fontSize="11"
          fill="#d4d4d8"
          fontFamily="ui-monospace, 'JetBrains Mono', monospace"
        >
          REVENGE-TRADE: 0
        </text>
      </g>
    </svg>
  );
}

function CardVisual({ id, accent }) {
  switch (id) {
    case "logic":
      return <ButterflyHarmonicVisual accent={accent} />;
    case "wisdom":
      return <BookStackVisual accent={accent} />;
    case "emotion":
      return <CelebrationVisual accent={accent} />;
    case "vision":
      return <GrowthCurveVisual accent={accent} />;
    case "mastermind":
      return <NeuralVisual accent={accent} />;
    default:
      return null;
  }
}

/* ─── SEARCH COMBOBOX ────────────────────────────────────────────────
   Top-center sticky search supporting "Official Name (TICKER)" lookup.
   Both ticker and full company name match the query (case-insensitive,
   substring). Keyboard-navigable (↑/↓/Enter/Esc), ARIA-labeled,
   focus-trapped while suggestions are open.
   ────────────────────────────────────────────────────────────────── */
function SearchCombobox({ onSelect }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const inputRef = useRef(null);
  const wrapRef = useRef(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return TICKER_INDEX.filter(
      (t) => t.ticker.toLowerCase().includes(q) || t.name.toLowerCase().includes(q),
    ).slice(0, 7);
  }, [query]);

  useEffect(() => {
    setHighlight(0);
  }, [query]);

  // close on outside click
  useEffect(() => {
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const commit = useCallback(
    (item) => {
      if (!item) return;
      onSelect?.(item);
      setQuery(`${item.name} (${item.ticker})`);
      setOpen(false);
      inputRef.current?.blur();
    },
    [onSelect],
  );

  const handleKey = (e) => {
    if (!open || matches.length === 0) {
      if (e.key === "ArrowDown" && matches.length > 0) {
        setOpen(true);
        e.preventDefault();
      }
      return;
    }
    if (e.key === "ArrowDown") {
      setHighlight((h) => (h + 1) % matches.length);
      e.preventDefault();
    } else if (e.key === "ArrowUp") {
      setHighlight((h) => (h - 1 + matches.length) % matches.length);
      e.preventDefault();
    } else if (e.key === "Enter") {
      commit(matches[highlight]);
      e.preventDefault();
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div ref={wrapRef} className="relative w-full max-w-2xl mx-auto">
      <div
        className={`group flex items-center gap-3 px-5 h-14 rounded-2xl bg-zinc-900/70 border transition-all ${
          open ? "border-cyan-400/50 shadow-[0_0_40px_-10px_rgba(34,211,238,0.4)]" : "border-zinc-800 hover:border-zinc-700"
        }`}
      >
        <Search
          className={`w-5 h-5 transition-colors ${open ? "text-cyan-300" : "text-zinc-500 group-hover:text-zinc-400"}`}
          aria-hidden="true"
        />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => query && setOpen(true)}
          onKeyDown={handleKey}
          placeholder="Search any equity — Apple Inc., AAPL, Volvo AB…"
          className="flex-1 bg-transparent outline-none text-zinc-100 placeholder:text-zinc-500 text-[15px]"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          aria-controls="ticker-listbox"
          aria-activedescendant={open && matches[highlight] ? `t-${matches[highlight].ticker}` : undefined}
          aria-label="Search equities by name or ticker"
          spellCheck={false}
          autoCorrect="off"
        />
        {query && (
          <button
            onClick={() => {
              setQuery("");
              setOpen(false);
              inputRef.current?.focus();
            }}
            className="p-1 rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800"
            aria-label="Clear search"
          >
            <X className="w-4 h-4" />
          </button>
        )}
        <kbd className="hidden sm:inline-flex items-center px-2 h-6 rounded-md border border-zinc-700 bg-zinc-800/60 text-[10px] font-mono text-zinc-400 tracking-wide">
          ⌘ K
        </kbd>
      </div>

      {open && matches.length > 0 && (
        <ul
          id="ticker-listbox"
          role="listbox"
          className="absolute left-0 right-0 mt-2 z-40 rounded-2xl border border-zinc-800 bg-zinc-950/95 backdrop-blur-xl shadow-2xl overflow-hidden"
        >
          {matches.map((m, i) => {
            const isOmx = m.exchange === "OMX";
            return (
              <li
                key={m.ticker}
                id={`t-${m.ticker}`}
                role="option"
                aria-selected={i === highlight}
                onMouseEnter={() => setHighlight(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  commit(m);
                }}
                className={`flex items-center gap-3 px-5 py-3 cursor-pointer transition-colors border-l-2 ${
                  i === highlight
                    ? "bg-zinc-900 border-cyan-400"
                    : "border-transparent hover:bg-zinc-900/60"
                }`}
              >
                <Building2 className="w-4 h-4 text-zinc-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-zinc-100 text-sm truncate">{m.name}</div>
                  <div className="flex items-center gap-2 text-[11px] mt-0.5">
                    <span
                      className="font-mono font-semibold text-cyan-300"
                      style={{ fontFamily: "ui-monospace, 'JetBrains Mono', monospace" }}
                    >
                      {m.ticker}
                    </span>
                    <span className="text-zinc-600">·</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      isOmx
                        ? "bg-amber-400/10 text-amber-300 border border-amber-400/20"
                        : "bg-zinc-800 text-zinc-400 border border-zinc-700"
                    }`}>
                      {m.exchange}
                    </span>
                  </div>
                </div>
                <ArrowRight className="w-4 h-4 text-zinc-600" />
              </li>
            );
          })}
        </ul>
      )}

      {open && query && matches.length === 0 && (
        <div className="absolute left-0 right-0 mt-2 z-40 rounded-2xl border border-zinc-800 bg-zinc-950/95 backdrop-blur-xl px-5 py-4 text-sm text-zinc-500">
          No matches for <span className="text-zinc-300">"{query}"</span>. Try a ticker or part of the company name.
        </div>
      )}
    </div>
  );
}

/* ─── CARD STACK ─────────────────────────────────────────────────────
   Bloomberg / Wallet-hybrid stacked card slider. The active card is
   centered and full-scale; other cards stack behind with progressive
   Y-offset and scale falloff. Click any visible card to make it active.
   Keyboard ←/→ cycle. Respects prefers-reduced-motion.
   ────────────────────────────────────────────────────────────────── */
function CardStack({ activeIndex, onSelect, selectedTicker }) {
  const reducedMotion = useReducedMotion();
  const total = CARDS.length;

  return (
    <div
      className="relative w-full max-w-3xl mx-auto"
      style={{ height: 520, perspective: 1600 }}
      role="region"
      aria-label="SENTRIQ pillars — stacked card slider"
    >
      {CARDS.map((card, i) => {
        const offset = (i - activeIndex + total) % total;
        const Icon = card.icon;
        const accent = ACCENT[card.accent];

        // Layout math — active=offset 0, behind cards stack down
        let translateY = offset * 22;
        let scale = 1 - offset * 0.045;
        let opacity = offset > 3 ? 0 : 1 - offset * 0.18;
        let zIndex = total - offset;
        let rotateX = offset === 0 ? 0 : -2 + offset * 0.4;
        const isActive = offset === 0;

        if (reducedMotion) {
          // flatten the stack for reduced-motion users
          translateY = isActive ? 0 : 540;
          scale = 1;
          rotateX = 0;
          opacity = isActive ? 1 : 0;
        }

        return (
          <article
            key={card.id}
            tabIndex={isActive ? 0 : -1}
            role="group"
            aria-label={`${card.eyebrow}: ${card.title}`}
            aria-current={isActive ? "true" : undefined}
            onClick={() => !isActive && onSelect(i)}
            onKeyDown={(e) => {
              if (!isActive) return;
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect((i + 1) % total);
              }
            }}
            className={`absolute left-0 right-0 top-0 mx-auto cursor-${
              isActive ? "default" : "pointer"
            } transition-all duration-500 ease-out will-change-transform`}
            style={{
              transform: `translateY(${translateY}px) scale(${scale}) rotateX(${rotateX}deg)`,
              opacity,
              zIndex,
              transformOrigin: "top center",
              transitionDuration: reducedMotion ? "0ms" : "500ms",
            }}
          >
            <div
              className={[
                "relative rounded-3xl overflow-hidden border h-[480px]",
                card.isVault
                  ? "bg-gradient-to-br from-violet-950/50 via-zinc-950 to-zinc-950 backdrop-blur-xl"
                  : "bg-gradient-to-br from-zinc-900 to-zinc-950",
                isActive ? `${accent.border} ${accent.glow}` : "border-zinc-800/70",
              ].join(" ")}
            >
              {/* Vault marker */}
              {card.isVault && (
                <div className="absolute top-5 right-5 z-10 flex items-center gap-1.5 px-3 py-1 rounded-full bg-violet-400/10 border border-violet-400/40 backdrop-blur">
                  <Lock className="w-3 h-3 text-violet-300" />
                  <span
                    className="text-[10px] font-semibold tracking-widest text-violet-200"
                    style={{ fontFamily: "ui-monospace, 'JetBrains Mono', monospace" }}
                  >
                    VAULT
                  </span>
                </div>
              )}

              {/* Header strip */}
              <div className="px-7 pt-7 pb-3 flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div
                    className={`w-10 h-10 rounded-xl flex items-center justify-center border ${accent.chip}`}
                  >
                    <Icon className="w-5 h-5" aria-hidden="true" />
                  </div>
                  <div>
                    <div
                      className={`text-[10px] font-semibold tracking-[0.2em] ${accent.text}`}
                      style={{ fontFamily: "ui-monospace, 'JetBrains Mono', monospace" }}
                    >
                      {card.eyebrow}
                    </div>
                    <h3 className="text-zinc-100 text-lg font-semibold leading-tight mt-0.5">
                      {card.title}
                    </h3>
                  </div>
                </div>
              </div>

              {/* Visual */}
              <div className="px-4 h-[260px] relative">
                <CardVisual id={card.id} accent={card.accent} />
              </div>

              {/* Body */}
              <div className="px-7 pb-7 pt-2">
                <p className="text-zinc-300 text-sm leading-relaxed">
                  <span className="text-zinc-100 font-medium">{card.subtitle}.</span>{" "}
                  {card.body}
                </p>
                <div className="mt-5 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-[11px] text-zinc-500">
                    <span
                      className="px-2 py-0.5 rounded border border-zinc-800 bg-zinc-900"
                      style={{ fontFamily: "ui-monospace, 'JetBrains Mono', monospace" }}
                    >
                      {selectedTicker ? selectedTicker : "context: portfolio"}
                    </span>
                    {card.apiSlot && (
                      <span
                        className="text-zinc-600"
                        style={{ fontFamily: "ui-monospace, 'JetBrains Mono', monospace" }}
                      >
                        slot: {card.apiSlot}
                      </span>
                    )}
                  </div>
                  {isActive && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelect((activeIndex + 1) % total);
                      }}
                      className={`flex items-center gap-1.5 text-xs font-medium ${accent.text} hover:brightness-125`}
                    >
                      Next pillar <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}

/* ─── REDUCED-MOTION HOOK ───────────────────────────────────────────
   Honor prefers-reduced-motion so the 3D card stack degrades gracefully
   for users who've requested less animation. Required for any
   institutional-grade UI.
   ────────────────────────────────────────────────────────────────── */
function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener?.("change", update);
    return () => mq.removeEventListener?.("change", update);
  }, []);
  return reduced;
}

/* ─── BACKGROUND ATMOSPHERE ─────────────────────────────────────────
   Subtle noise + radial gradient. Pure CSS / SVG, no external assets.
   ────────────────────────────────────────────────────────────────── */
function Atmosphere() {
  return (
    <div className="absolute inset-0 -z-10 overflow-hidden pointer-events-none">
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(900px 500px at 50% -100px, rgba(34,211,238,0.10), transparent 60%), radial-gradient(700px 400px at 90% 60%, rgba(167,139,250,0.08), transparent 60%), radial-gradient(600px 300px at 10% 80%, rgba(56,189,248,0.06), transparent 60%)",
        }}
      />
      <svg className="absolute inset-0 w-full h-full opacity-[0.035]" aria-hidden="true">
        <filter id="grain">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch" />
          <feColorMatrix values="0 0 0 0 1   0 0 0 0 1   0 0 0 0 1   0 0 0 1 0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#grain)" />
      </svg>
    </div>
  );
}

/* ─── ROOT ──────────────────────────────────────────────────────────── */
export default function App() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [selectedTicker, setSelectedTicker] = useState(null);

  // Global keyboard navigation for the card stack
  useEffect(() => {
    const handler = (e) => {
      const tag = (e.target?.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea") return;
      if (e.key === "ArrowRight") {
        setActiveIndex((i) => (i + 1) % CARDS.length);
      } else if (e.key === "ArrowLeft") {
        setActiveIndex((i) => (i - 1 + CARDS.length) % CARDS.length);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <div
      className="relative min-h-screen w-full bg-[#08090d] text-zinc-100 overflow-x-hidden"
      style={{ fontFamily: "'Inter', system-ui, -apple-system, sans-serif" }}
    >
      <Atmosphere />

      {/* Top bar — sticky */}
      <header className="sticky top-0 z-30 backdrop-blur-xl bg-[#08090d]/70 border-b border-zinc-900">
        <div className="max-w-7xl mx-auto flex items-center gap-4 px-6 py-4">
          {/* Logo */}
          <div className="flex items-center gap-2.5 shrink-0">
            <div className="relative w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-400 to-violet-500 flex items-center justify-center">
              <div className="absolute inset-0.5 rounded-md bg-[#08090d] flex items-center justify-center">
                <Sparkles className="w-4 h-4 text-cyan-300" />
              </div>
            </div>
            <div className="flex items-baseline gap-1">
              <span className="text-[15px] font-semibold tracking-tight">SENTRIQ</span>
              <span
                className="text-[10px] text-zinc-500 tracking-widest"
                style={{ fontFamily: "ui-monospace, 'JetBrains Mono', monospace" }}
              >
                v0.1
              </span>
            </div>
          </div>

          {/* Search — primary hero, top-center */}
          <div className="flex-1">
            <SearchCombobox onSelect={(t) => setSelectedTicker(`${t.ticker}`)} />
          </div>

          {/* Tier nav */}
          <nav className="hidden md:flex items-center gap-1 shrink-0">
            {[
              { label: "Free", color: "text-zinc-400" },
              { label: "Pro", color: "text-cyan-300" },
              { label: "Vault", color: "text-violet-300" },
            ].map((t) => (
              <button
                key={t.label}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-zinc-900 transition-colors ${t.color}`}
              >
                {t.label}
              </button>
            ))}
            <button className="ml-2 px-4 py-1.5 rounded-lg text-xs font-semibold bg-cyan-400 hover:bg-cyan-300 text-zinc-950 transition-colors">
              Sign in
            </button>
          </nav>
        </div>
      </header>

      {/* Hero strip */}
      <section className="max-w-7xl mx-auto px-6 pt-16 pb-8 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-zinc-800 bg-zinc-900/50 mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span
            className="text-[11px] tracking-wide text-zinc-400"
            style={{ fontFamily: "ui-monospace, 'JetBrains Mono', monospace" }}
          >
            transparent signal hub · OpenBB-powered
          </span>
        </div>
        <h1 className="text-4xl sm:text-5xl md:text-6xl font-semibold tracking-tight leading-[1.05] max-w-3xl mx-auto">
          The trading platform that <span className="text-cyan-300">shows its work.</span>
        </h1>
        <p className="mt-5 text-zinc-400 text-base sm:text-lg max-w-xl mx-auto leading-relaxed">
          Five pillars. One thesis. SENTRIQ pairs institutional-grade signals with the psychological discipline that lets you actually use them.
        </p>
        <div className="mt-7 flex items-center justify-center gap-3 text-[11px] text-zinc-500">
          <span className="flex items-center gap-1.5">
            <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 font-mono">←</kbd>
            <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 font-mono">→</kbd>
            cycle pillars
          </span>
          <span className="text-zinc-700">·</span>
          <span>click any card to bring it forward</span>
        </div>
      </section>

      {/* The interactive core */}
      <section className="max-w-7xl mx-auto px-6 pb-12">
        <CardStack
          activeIndex={activeIndex}
          onSelect={setActiveIndex}
          selectedTicker={selectedTicker}
        />
      </section>

      {/* Card navigator dots */}
      <section className="max-w-3xl mx-auto px-6 pb-16">
        <div className="flex items-center justify-between gap-2 px-4 py-3 rounded-2xl border border-zinc-900 bg-zinc-950/60">
          <button
            onClick={() => setActiveIndex((i) => (i - 1 + CARDS.length) % CARDS.length)}
            className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900"
            aria-label="Previous pillar"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <div className="flex-1 flex items-center justify-center gap-2">
            {CARDS.map((c, i) => {
              const a = ACCENT[c.accent];
              const isActive = i === activeIndex;
              return (
                <button
                  key={c.id}
                  onClick={() => setActiveIndex(i)}
                  aria-label={`Go to ${c.title}`}
                  aria-current={isActive ? "true" : undefined}
                  className={`group flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all ${
                    isActive ? "bg-zinc-900" : "hover:bg-zinc-900/50"
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full transition-all ${
                      isActive ? `${a.fill}` : "bg-zinc-700 group-hover:bg-zinc-500"
                    }`}
                  />
                  <span
                    className={`text-[11px] tracking-wider font-medium hidden sm:inline ${
                      isActive ? a.text : "text-zinc-500 group-hover:text-zinc-300"
                    }`}
                    style={{ fontFamily: "ui-monospace, 'JetBrains Mono', monospace" }}
                  >
                    {c.eyebrow.split("/")[0].trim()}
                  </span>
                </button>
              );
            })}
          </div>
          <button
            onClick={() => setActiveIndex((i) => (i + 1) % CARDS.length)}
            className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900"
            aria-label="Next pillar"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </section>

      {/* Footer thesis */}
      <footer className="max-w-7xl mx-auto px-6 pb-16">
        <div className="rounded-2xl border border-zinc-900 bg-zinc-950/40 px-6 py-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <p className="text-zinc-400 text-sm max-w-2xl">
            SENTRIQ is the frontend layer of an OpenBB-powered trading intelligence stack. Signals are computed deterministically; the psychology layer is the differentiator.
          </p>
          <div className="flex items-center gap-3 shrink-0">
            <span
              className="text-[11px] text-zinc-600"
              style={{ fontFamily: "ui-monospace, 'JetBrains Mono', monospace" }}
            >
              build:0.1.0 · stockholm
            </span>
            <button className="px-4 py-2 rounded-lg text-xs font-semibold border border-cyan-400/40 text-cyan-200 hover:bg-cyan-400/10 transition-colors">
              Request Vault access
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
