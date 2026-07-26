"""Hardening tests for Steps 11-17 (MTF chart, near-miss, proximity, pitchfork).

Standalone (no pytest needed): exits non-zero if any check fails.
Run:  source venv/bin/activate && python test_mtf_proximity_hardening.py
Covers edge cases the curl smoke tests did not: threshold boundaries, degenerate
geometry, tiny/flat inputs, no-exception guarantees, and lean-value validity.
"""
from __future__ import annotations
import math, sys
import pandas as pd

from pages.ai_trading_agent import (
    harmonic_near_miss, compute_proximity_readouts, compute_andrews_pitchfork,
    RSI_OVERBOUGHT, RSI_OVERSOLD,
)

FAILS: list[str] = []
def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)

VALID_LEANS = {"bullish", "bearish", "neutral"}

# ---------- harmonic_near_miss ----------
print("harmonic_near_miss:")
check("empty -> None", harmonic_near_miss([]) is None)
check("<4 swings -> None", harmonic_near_miss([(0,1.0),(1,2.0),(2,1.5)]) is None)
flat = [(i, 100.0) for i in range(8)]              # flat prices must not raise / not div0
try:
    r_flat = harmonic_near_miss(flat); check("flat prices no-raise", True)
    check("flat prices -> None or safe dict", r_flat is None or isinstance(r_flat, dict))
except Exception as e:
    check("flat prices no-raise", False, repr(e))
swings = [(0,100.0),(5,140.0),(10,118.0),(15,150.0),(20,112.0),(25,155.0),(30,120.0)]
nm = harmonic_near_miss(swings)
check("valid swings -> dict", isinstance(nm, dict))
if isinstance(nm, dict):
    check("has required keys", all(k in nm for k in ("pattern","direction","d_price","prz_low","prz_high","miss","pivot_idx")))
    check("miss finite & >=0", isinstance(nm["miss"],(int,float)) and math.isfinite(nm["miss"]) and nm["miss"]>=0)
    check("prz_low <= prz_high", nm["prz_low"] <= nm["prz_high"])
    check("direction valid", nm["direction"] in ("bullish","bearish"))
    check("all prz finite", all(math.isfinite(nm[k]) for k in ("d_price","prz_low","prz_high")))

# ---------- compute_proximity_readouts ----------
print("compute_proximity_readouts:")
check("all-None -> [] no-raise", compute_proximity_readouts(None,None,None,None,None,None,None,None,None,None,None,None)==[])

def prox(**kw):
    base=dict(last_price=100.0,rsi=None,macd_line=None,macd_signal=None,macd_hist=None,
              bb_upper=None,bb_lower=None,price_vs_cloud="UNKNOWN",cloud_top=None,cloud_bot=None,
              tk_cross="NEUTRAL",wave_phase="NONE")
    base.update(kw)
    return compute_proximity_readouts(base["last_price"],base["rsi"],base["macd_line"],base["macd_signal"],
        base["macd_hist"],base["bb_upper"],base["bb_lower"],base["price_vs_cloud"],base["cloud_top"],
        base["cloud_bot"],base["tk_cross"],base["wave_phase"])

def one(rs, name): 
    return next((x for x in rs if x["name"]==name), None)

# RSI threshold boundaries (exact == values must classify correctly, tolerance-safe)
r_ob = one(prox(rsi=float(RSI_OVERBOUGHT)),"RSI"); check("RSI==70 -> overbought/bearish", r_ob and r_ob["state"]=="overbought" and r_ob["lean"]=="bearish")
r_os = one(prox(rsi=float(RSI_OVERSOLD)),"RSI");  check("RSI==30 -> oversold/bullish",  r_os and r_os["state"]=="oversold"  and r_os["lean"]=="bullish")
r_50 = one(prox(rsi=50.0),"RSI");                 check("RSI==50 -> neutral/neutral",   r_50 and r_50["state"]=="neutral"   and r_50["lean"]=="neutral")
r_60 = one(prox(rsi=59.7),"RSI");                 check("RSI 59.7 -> neutral/bullish",  r_60 and r_60["state"]=="neutral"   and r_60["lean"]=="bullish")
# MACD histogram exactly zero
m0 = one(prox(macd_hist=0.0),"MACD"); check("MACD hist==0 -> at crossover/neutral", m0 and m0["state"]=="at crossover" and m0["lean"]=="neutral")
mp = one(prox(macd_hist=0.5),"MACD"); check("MACD hist>0 -> bullish", mp and mp["lean"]=="bullish")
mn = one(prox(macd_hist=-0.5),"MACD");check("MACD hist<0 -> bearish", mn and mn["lean"]=="bearish")
# Bollinger price exactly on bands
bu = one(prox(last_price=110.0,bb_upper=110.0,bb_lower=90.0),"Bollinger"); check("price==upper -> at/above", bu and "upper" in bu["state"])
bl = one(prox(last_price=90.0, bb_upper=110.0,bb_lower=90.0),"Bollinger"); check("price==lower -> at/below", bl and "lower" in bl["state"])
bi = one(prox(last_price=105.0,bb_upper=110.0,bb_lower=90.0),"Bollinger"); check("price inside -> bullish lean (above mid)", bi and bi["state"]=="inside bands" and bi["lean"]=="bullish")
# Ichimoku states
ia = one(prox(price_vs_cloud="ABOVE",cloud_top=95.0,cloud_bot=90.0),"Ichimoku"); check("ichimoku ABOVE -> bullish", ia and ia["lean"]=="bullish")
ib = one(prox(price_vs_cloud="BELOW",cloud_top=110.0,cloud_bot=105.0),"Ichimoku"); check("ichimoku BELOW -> bearish", ib and ib["lean"]=="bearish")
ii = one(prox(price_vs_cloud="INSIDE",cloud_top=105.0,cloud_bot=95.0,tk_cross="BULL"),"Ichimoku"); check("ichimoku INSIDE+BULL -> bullish", ii and ii["lean"]=="bullish")
check("ichimoku UNKNOWN -> omitted", one(prox(price_vs_cloud="UNKNOWN"),"Ichimoku") is None)
# Elliott phases
check("elliott W3_COMPLETE present", one(prox(wave_phase="W3_COMPLETE"),"Elliott Wave") is not None)
check("elliott W5_REVERSAL present", one(prox(wave_phase="W5_REVERSAL"),"Elliott Wave") is not None)
check("elliott NONE -> omitted", one(prox(wave_phase="NONE"),"Elliott Wave") is None)
# Global invariants on a fully-populated readout
full = prox(rsi=59.7,macd_hist=0.3,bb_upper=110.0,bb_lower=90.0,price_vs_cloud="ABOVE",cloud_top=95.0,cloud_bot=90.0,wave_phase="W3_COMPLETE")
check("all leans valid", all(x["lean"] in VALID_LEANS for x in full))
check("all have name/state/to/note", all(all(k in x for k in ("name","state","to","note")) for x in full))

# ---------- compute_andrews_pitchfork ----------
print("compute_andrews_pitchfork:")
df = pd.DataFrame({"close":[100.0+i for i in range(40)]})
check("<3 swings -> None", compute_andrews_pitchfork([(0,1.0),(1,2.0)], df) is None)
check("empty df -> None", compute_andrews_pitchfork(swings, pd.DataFrame()) is None)
# degenerate: midpoint x == p0 x -> dx 0 -> must return None (no ZeroDivisionError)
try:
    deg = compute_andrews_pitchfork([(10,100.0),(0,90.0),(20,110.0)], df); check("degenerate dx=0 no-raise", True)
    check("degenerate -> None", deg is None)
except Exception as e:
    check("degenerate dx=0 no-raise", False, repr(e))
pf = compute_andrews_pitchfork(swings, df)
check("valid -> dict", isinstance(pf, dict))
if isinstance(pf, dict):
    check("has lines_idx", "lines_idx" in pf and all(k in pf["lines_idx"] for k in ("median","rail1","rail2")))
    check("lower <= upper", pf["lower"] <= pf["upper"])
    check("lines have 2 endpoints", all(len(pf["lines_idx"][k])==2 for k in ("median","rail1","rail2")))
    check("all levels finite", all(math.isfinite(pf[k]) for k in ("median","upper","lower","last_price")))
    check("position valid", pf["position"] in ("above upper rail","below lower rail","upper half","lower half","on median"))

print()
if FAILS:
    print(f"RESULT: {len(FAILS)} FAILED -> {FAILS}"); sys.exit(1)
print("RESULT: ALL ENGINE HARDENING CHECKS PASSED")
