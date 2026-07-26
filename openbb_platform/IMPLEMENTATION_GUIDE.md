# 🚀 UNIFIED PROJECT IMPLEMENTATION GUIDE

## Executive Summary

You now have a **unified full-stack architecture** where:

✅ **Backend** (Python): OpenBB + FastAPI + Streamlit = `localhost:8000` + `localhost:8501`
✅ **Frontend** (React): Sentriq website = `localhost:5173`
✅ **Integration**: React calls `/api/*` → Python engine (100% code reuse, zero duplication)
✅ **Domain**: `.com` domain ready for deployment (see DEPLOYMENT.md)
✅ **Scripts**: Ready to launch all services with one command

---

## Current Project Status

### ✅ Completed
- [x] **Fresh venv created** with Python 3.14.2
- [x] **Startup scripts** (`start_all.sh`, `setup_project.sh`) ready
- [x] **Architecture documentation** (ARCHITECTURE.md)
- [x] **Deployment guide** with domain setup (DEPLOYMENT.md)
- [x] **React API client** template (api_client_template.ts)
- [x] **Vite proxy config** template (vite_config_template.ts)

### ⏳ Next Steps for You

---

## STEP 1: Install Python Dependencies (5 minutes)

Your venv is ready. Install required packages:

```bash
cd "/Users/javadurant/Documents/Javad Trading Project/GitHub/OpenBB/openbb_platform"
source venv/bin/activate
pip install -r requirements.txt
```

**If requirements.txt is missing**, run:
```bash
bash setup_project.sh
```

---

## STEP 2: Configure Environment Variables (5 minutes)

Create/update `.env` file with your API keys:

```bash
# Copy template
cp .env.example .env  # (if it exists)

# Or create new .env with your keys:
cat > .env << 'EOF'
# OpenAI / Claude API
OPENAI_API_KEY=sk-your-key-here
GROQ_API_KEY=gsk_your-key-here

# Financial Data APIs
FRED_API_KEY=your-key
TIINGO_API_KEY=your-key
ALPHA_VANTAGE_API_KEY=your-key
FMP_API_KEY=your-key

# Frontend
FRONTEND_URL=http://localhost:5173
API_URL=http://localhost:8000

# Debug
DEBUG_MODE=true
EOF
```

---

## STEP 3: Setup React App (10 minutes)

Move your Sentriq project into the unified structure:

### Option A: If Sentriq is already in `/sentriq/` folder
```bash
# Nothing to do! It's already in the right place.
# Just verify it has node_modules:
cd sentriq
npm install
cd ..
```

### Option B: If Sentriq is in a different location
```bash
# 1. Copy it into the project
cp -r /path/to/sentriq ./sentriq

# 2. Install dependencies
cd sentriq
npm install  # or: pnpm install
cd ..
```

### Step 3b: Update Vite Config
Replace your `sentriq/vite.config.ts` with our template:

```bash
cp vite_config_template.ts sentriq/vite.config.ts
```

This configures the proxy: `localhost:5173/api/*` → `localhost:8000/api/*`

### Step 3c: Setup React API Client

Copy the TypeScript API client into your React project:

```bash
cp api_client_template.ts sentriq/src/services/openbbClient.ts
```

Now, in your React components, use it like:

```typescript
// sentriq/src/components/SignalsPanel.tsx
import { getSignals } from '../services/openbbClient';

function SignalsPanel() {
  const [signals, setSignals] = useState(null);
  
  useEffect(() => {
    const fetchSignals = async () => {
      const data = await getSignals({ symbol: 'AAPL' });
      setSignals(data);
    };
    fetchSignals();
  }, []);
  
  return <div>{/* Display signals */}</div>;
}
```

---

## STEP 4: Update FastAPI Routes (15 minutes)

Make sure your `api/routes/` has all the endpoints your React app needs:

### Example: `api/routes/signals.py`

```python
from fastapi import APIRouter
from pages.ai_trading_agent import get_signals  # Call YOUR existing code

router = APIRouter()

@router.post("/api/signals")
async def signals(symbol: str, timeframe: str = "daily"):
    """Get trading signals for a symbol"""
    # Call your existing Python function
    result = get_signals(symbol, timeframe)
    return {"symbol": symbol, "signals": result}
```

### Register route in `api/main.py`:

```python
from fastapi import FastAPI
from api.routes import signals

app = FastAPI()
app.include_router(signals.router)

@app.get("/health")
def health():
    return {"status": "ok"}
```

---

## STEP 5: Launch Everything (1 minute)

### All Services at Once
```bash
bash start_all.sh
```

This script:
- Activates venv
- Starts FastAPI (8000)
- Starts Streamlit (8501)
- Starts React (5173)

### Or start individually:

```bash
# Terminal 1: FastAPI
source venv/bin/activate
uvicorn api.main:app --reload

# Terminal 2: Streamlit
source venv/bin/activate
streamlit run app.py

# Terminal 3: React
cd sentriq
npm run dev
```

---

## STEP 6: Verify Everything Works

### Checklist

```bash
# 1. FastAPI Health Check
curl http://localhost:8000/docs
# Should see interactive Swagger docs

# 2. Streamlit Running
open http://localhost:8501
# Should see your dashboard

# 3. React Frontend
open http://localhost:5173
# Should see Sentriq website

# 4. API Communication
curl http://localhost:8000/api/health
# Should return {"status": "ok"}
```

---

## STEP 7: Deploy to Your .com Domain (Optional, for production)

See **DEPLOYMENT.md** for:

1. **Register domain**: Cloudflare ($8.85/year)
2. **Rent VPS**: DigitalOcean ($5/month)
3. **Deploy app**: Docker + Nginx
4. **SSL/HTTPS**: Automatic with Cloudflare

**Recommended domain**: `sentriq.com` or `sentriqai.com`

---

## File Reference

| File | Purpose | Created |
|------|---------|---------|
| `start_all.sh` | Launch all services | ✅ Ready |
| `setup_project.sh` | Initial setup | ✅ Ready |
| `ARCHITECTURE.md` | Project structure | ✅ Ready |
| `DEPLOYMENT.md` | Domain + cloud setup | ✅ Ready |
| `api_client_template.ts` | React API client | ✅ Ready |
| `vite_config_template.ts` | Vite proxy config | ✅ Ready |
| `.env` | Environment variables | ⏳ You create |
| `api/routes/*.py` | Your API endpoints | ⏳ You update |
| `sentriq/vite.config.ts` | Vite config | ⏳ Copy template |
| `sentriq/src/services/openbbClient.ts` | API client | ⏳ Copy template |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    sentriq.com (Your Domain)                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │   Streamlit  │    │   FastAPI    │    │    React     │   │
│  │   Dashboard  │    │     Keys     │    │   Frontend   │   │
│  │   :8501      │    │     :8000    │    │   :5173      │   │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘   │
│         │                    │                    │            │
│         └────────────────────┼────────────────────┘            │
│                              │                                 │
│                    Requests → /api/* ← ←                      │
│                              │                                 │
│         ┌────────────────────▼────────────────────┐           │
│         │   Your Python Analysis Engine          │           │
│         ├────────────────────────────────────────┤           │
│         │ • pages/ai_trading_agent.py            │           │
│         │ • engine/prediction/                   │           │
│         │ • extensions/equity/                   │           │
│         │ • providers/*/                         │           │
│         │ (ALL YOUR EXISTING CODE)               │           │
│         └────────────────────────────────────────┘           │
│              ↓                                                │
│         ┌────────────────────────────────────────┐           │
│         │   External Data Sources                │           │
│         ├────────────────────────────────────────┤           │
│         │ • FRED API                             │           │
│         │ • Tiingo                               │           │
│         │ • Yahoo Finance                        │           │
│         │ • Polygon                              │           │
│         │ • OpenBB Extensions                    │           │
│         └────────────────────────────────────────┘           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow Example: User Searches for Trading Signal

```
1. User types "AAPL" in React Frontend
   ↓
2. React calls: getSignals({ symbol: 'AAPL' })
   ↓
3. Axios request: POST http://localhost:5173/api/signals
   ↓
4. Vite proxy intercepts: forwards to http://localhost:8000/api/signals
   ↓
5. FastAPI router receives request
   ↓
6. Calls your Python code: pages.ai_trading_agent.get_signals('AAPL')
   ↓
7. Your code:
   - Fetches data from FRED/Tiingo
   - Runs analysis with engine/prediction/
   - Returns results
   ↓
8. FastAPI returns: { symbol: 'AAPL', signals: {...} }
   ↓
9. React receives JSON, updates UI
   ↓
10. User sees live trading signals! ✅
```

---

## Common Tasks After Setup

### Adding a New API Endpoint

```python
# 1. Create api/routes/my_feature.py
from fastapi import APIRouter
from pages import my_module

router = APIRouter()

@router.post("/api/my-feature")
def my_feature(param: str):
    result = my_module.analyze(param)
    return result

# 2. Register in api/main.py
from api.routes import my_feature
app.include_router(my_feature.router)

# 3. Call from React
const result = await openbbClient.post('/api/my-feature', { param: 'value' });
```

### Calling Your Endpoint from React

```typescript
import { openbbClient } from '../services/openbbClient';

function MyComponent() {
  const [data, setData] = useState(null);
  
  useEffect(() => {
    async function fetch() {
      const result = await openbbClient.post('/api/my-feature', { param });
      setData(result.data);
    }
    fetch();
  }, []);
  
  return <div>{/* Display data */}</div>;
}
```

### Running Tests

```bash
# Python tests
source venv/bin/activate
pytest tests/

# React tests
cd sentriq
npm run test
```

---

## Troubleshooting

### Port Already in Use
```bash
# Find process using port 8000
lsof -i :8000
# Kill it
kill -9 PID

# Or change port in .env
FASTAPI_PORT=8001
```

### React can't reach API
```bash
# Check proxy in sentriq/vite.config.ts
# Verify FastAPI is running: curl http://localhost:8000/docs
# Check CORS: add to api/main.py:
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Dependencies Not Installing
```bash
# Clear pip cache
pip cache purge

# Reinstall requirements
pip install -r requirements.txt --force-reinstall
```

---

## Next Steps

1. ✅ **Now**: Run `bash setup_project.sh` to finalize setup
2. ⏳ **Today**: Update `.env` with API keys  
3. ⏳ **Today**: Run `bash start_all.sh` to launch all services
4. ⏳ **This week**: Deploy to `sentriq.com` (see DEPLOYMENT.md)

---

## Support

- **Architecture questions** → See ARCHITECTURE.md
- **Deployment help** → See DEPLOYMENT.md
- **API client docs** → See api_client_template.ts
- **Project structure** → See folder tree above

---

**Created**: April 15, 2026
**Status**: 🟢 READY TO RUN
**Next Action**: Run `bash setup_project.sh`
