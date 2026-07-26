"""Endpoint hardening: strict JSON-finite, error paths, fallback. Backend must be up on :8000."""
import json, sys, urllib.request, urllib.error
BASE="http://127.0.0.1:8000"
FAILS=[]
def check(n,c,d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}"+(f"  -- {d}" if (d and not c) else "")); 
    if not c: FAILS.append(n)
def _raise_nonfinite(x): raise ValueError(f"non-finite literal: {x}")
def get(path):
    """returns (status, parsed_or_None). Strict: NaN/Infinity -> ValueError."""
    try:
        with urllib.request.urlopen(BASE+path, timeout=40) as r:
            txt=r.read().decode()
            return r.status, json.loads(txt, parse_constant=_raise_nonfinite)
    except urllib.error.HTTPError as e:
        return e.code, None

print("/chart JSON-finite + fallback:")
for sym in ("AAPL","NDA-SE.ST"):
    for tf in ("daily","weekly","monthly","hourly"):
        try:
            st,d=get(f"/api/symbol/{sym}/chart?tf={tf}")
            ok = st==200 and isinstance(d,dict) and d.get("status")=="ok" and isinstance(d.get("candles"),list) and len(d["candles"])>0
            check(f"{sym} {tf} ok+finite+candles", ok, f"status={st}")
        except ValueError as e:
            check(f"{sym} {tf} ok+finite+candles", False, str(e))
# garbage tf -> must fall back to daily (not 4xx/5xx)
try:
    st,d=get("/api/symbol/AAPL/chart?tf=garbage"); check("garbage tf -> daily fallback", st==200 and d and d.get("timeframe")=="daily", f"status={st} tf={d.get('timeframe') if d else None}")
except ValueError as e:
    check("garbage tf -> daily fallback", False, str(e))
# bad symbol -> 404 (graceful), not 500
st,d=get("/api/symbol/ZZZZ.INVALID/chart?tf=daily"); check("bad symbol -> 404 not 500", st==404, f"status={st}")

print("/technical proximity + pitchfork + finite:")
try:
    st,d=get("/api/symbol/AAPL/technical")
    check("technical 200+finite", st==200 and isinstance(d,dict))
    if isinstance(d,dict):
        check("proximity is list & non-empty", isinstance(d.get("proximity"),list) and len(d["proximity"])>0)
        check("pitchfork key present", "pitchfork" in d)
        leans={x.get("lean") for x in d.get("proximity",[])}
        check("proximity leans valid", leans <= {"bullish","bearish","neutral"}, str(leans))
except ValueError as e:
    check("technical 200+finite", False, str(e))

print()
if FAILS: print(f"RESULT: {len(FAILS)} FAILED -> {FAILS}"); sys.exit(1)
print("RESULT: ALL ENDPOINT HARDENING CHECKS PASSED")
