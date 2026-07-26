# 🚀 UNIFIED OpenBB + Sentriq Project Architecture

## Project Overview

This is a **unified full-stack financial platform** combining:
- **Backend**: OpenBB Platform (Python) + FastAPI REST API + Streamlit Dashboard
- **Frontend**: React + TypeScript (Sentriq)
- **Domain**: Custom .com domain (see deployment docs)

## Directory Structure

```
openbb_platform/
├── app.py                          # Streamlit main dashboard (port 8501)
├── pages/                          # Streamlit pages (your analysis tools)
├── engine/                         # Core trading engine & analysis
├── extensions/                     # OpenBB extensions
├── providers/                      # Data providers
│
├── api/                            # REST API (FastAPI)
│   ├── main.py                    # FastAPI app entry point
│   └── routes/                    # API endpoints
│       ├── signals.py
│       ├── analytics.py
│       ├── market.py
│       └── ai_insights.py
│
├── sentriq/                        # React Frontend (Vite)
│   └── src/
│       ├── pages/
│       ├── components/
│       ├── services/
│       │   └── openbbClient.ts    # API client (connects to /api/*)
│       └── App.tsx
│
├── start_all.sh                    # Launch all services
├── setup_project.sh                # Initial setup
├── requirements.txt                # Python dependencies
├── .env                            # Environment variables
└── ARCHITECTURE.md                 # This file
```

## How Data Flows

```
React Component (localhost:5173)
        ↓
    useQuery() hook
        ↓
    openbbClient.ts (Axios)
        ↓
    Vite proxy → /api/* → localhost:8000
        ↓
    FastAPI Router (api/routes/)
        ↓
    Your Python Engine 
    (pages/, engine/, extensions/)
        ↓
    REST JSON Response
        ↓
    React Re-renders with live data
```

## Services

### Backend (Port 8000)
- **FastAPI REST API**
  - Documentation: http://localhost:8000/docs
  - Endpoints: `/api/signals`, `/api/analytics`, `/api/market`, `/api/ai_insights`

### Streamlit Dashboard (Port 8501)
- **Your trading dashboard**: http://localhost:8501
- Runs alongside FastAPI (both active simultaneously)

### React Frontend (Port 5173)
- **Sentriq website**: http://localhost:5173
- Proxies API calls to FastAPI

## Getting Started

### 1. Initial Setup
```bash
bash setup_project.sh
```

### 2. Update Environment Variables
```bash
# Edit .env with your API keys:
# - OPENAI_API_KEY
# - GROQ_API_KEY
# - FRED_API_KEY
# - etc.
```

### 3. Start Everything
```bash
bash start_all.sh
```

### 4. Open in Browser
- Backend API: http://localhost:8000/docs
- Streamlit: http://localhost:8501
- React Frontend: http://localhost:5173

## Development Workflow

### Adding a New API Endpoint

1. **Create route** in `api/routes/new_feature.py`:
```python
from fastapi import BaseModel

class MyRequest(BaseModel):
    symbol: str

@router.post("/my-endpoint")
def my_endpoint(request: MyRequest):
    # Call your existing Python code
    result = your_analysis_function(request.symbol)
    return {"result": result}
```

2. **Register route** in `api/main.py`:
```python
from api.routes import new_feature
app.include_router(new_feature.router, prefix="/api")
```

3. **Call from React**:
```typescript
const response = await openbbClient.post('/my-endpoint', { symbol: 'AAPL' });
```

## Key Files to Understand

- `app.py`: Streamlit entry point (your existing dashboard)
- `api/main.py`: FastAPI application
- `sentriq/vite.config.ts`: Proxy configuration for API calls
- `sentriq/src/services/openbbClient.ts`: Axios client for API calls
- `.env`: All secrets and configuration

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 19 + TypeScript + Vite |
| **API** | FastAPI + Uvicorn |
| **Backend** | Python 3.14 + OpenBB + Streamlit |
| **Data** | Multiple providers (FRED, Tiingo, Polygon, etc.) |
| **AI** | Groq + Claude API integration |
| **Package Manager** | pip (Python), pnpm (Node) |

## Deployment

See `DEPLOYMENT.md` for:
- Docker setup
- Cloud deployment (AWS, Railway, Render)
- Custom domain configuration (.com)
- HTTPS/SSL setup

## Troubleshooting

### venv issues
```bash
rm -rf venv
python3.14 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Port conflicts
- Change `FASTAPI_PORT` in `.env` if 8000 is busy
- Change `STREAMLIT_SERVER_PORT` if 8501 is busy
- Vite uses 5173 by default

### API not responding from React
Check `sentriq/vite.config.ts` proxy configuration matches your backend port

## Next Steps

1. Verify both `start_all.sh` and `setup_project.sh` are executable
2. Run `bash setup_project.sh`
3. Update `.env` with your API keys
4. Run `bash start_all.sh`
5. Access all three services simultaneously

---
**Last Updated**: April 15, 2026
**Version**: 1.0.0
