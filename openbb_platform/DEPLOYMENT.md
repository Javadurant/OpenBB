# 🌐 Deployment & Domain Setup Guide

## Custom .com Domain Options

### Recommended Domain Registrars (2026)

#### **1. Cloudflare Domains (BEST FOR THIS PROJECT)**
- **URL**: https://www.cloudflare.com/products/registrar/
- **Price**: $8.85/year (no markup, at-cost pricing)
- **Renewal**: $8.85/year (guaranteed)
- **Why for your project**: 
  - Incredible value
  - Auto-SSL (HTTPS for free)
  - DDoS protection for APIs
  - Free email forwarding
  - Best for AI/Finance APIs

#### **2. Namecheap** 
- **URL**: https://www.namecheap.com
- **Price**: ~$8.98/year first, $10.98 renewal
- **Why**: Budget-friendly, good support

#### **3. Google Domains** (Now Squarespace)
- **URL**: https://www.squarespace.com/
- **Price**: $12/year
- **Why**: Simple, integrated with Google services

#### **4. Domain.com**
- **URL**: https://www.domain.com
- **Price**: ~$9.99/year
- **Why**: Competitive pricing

---

## Suggested Domain Names for Your Project

Given your project combines OpenBB + Sentriq + AI Trading:

### 🎯 Recommended (Most Professional)
- `sentriq.com` - **Your brand, memorable** ⭐
- `sentriqai.com` - Emphasizes AI
- `sentriqtrading.com` - Clear purpose

### Alternative Options
- `openbbsentriq.com` - Combines both
- `tradeit.ai` - Simple, modern
- `financialsentryiq.com` - Descriptive
- `stoxai.com` - Tech-forward

### Domain Registration Steps

1. **Go to Cloudflare Domains**: https://www.cloudflare.com/products/registrar/
2. **Search your domain** (e.g., `sentriq.com`)
3. **Add to cart & checkout**
4. **Point DNS to your deployment** (see below)

---

## Deployment Architectures

### Option A: Single VPS (Recommended for Starting)
**Cost**: ~$10-20/month

```
Your Domain (sentriq.com)
    ↓
Cloudflare DNS (free)
    ↓
VPS (DigitalOcean, Linode, Hetzner)
    ↓
Docker Container (all services together)
    ├── FastAPI (port 8000, internal)
    ├── Streamlit (port 8501, internal)
    └── React (built as static, served by Nginx)
    ↓
Nginx Reverse Proxy (port 80/443)
```

**Recommended Providers:**
- **DigitalOcean**: $5-6/month (droplet)
- **Linode**: $5-6/month (simple Linux)
- **Hetzner**: €3-4/month (cheapest, excellent)
- **Railway**: $5+/month (easiest for Python apps)

### Option B: Serverless (Most Scalable)
**Cost**: ~$20-50/month (pay per use after free tier)

```
sentriq.com
    ↓
Netlify/Vercel (React frontend) - FREE
    ↓
Railway/Render/Heroku (FastAPI backend)
    ↓
AWS Lambda or Google Cloud (Streamlit - paid)
```

### Option C: Full Managed (Easiest, Not Cheapest)
**Cost**: ~$50-100+/month

- **Vercel** (frontend only) - $20+
- **Fly.io** (full stack) - $15+
- **Render** (full stack) - $30+
- **AWS** (full stack) - variable, usually expensive

---

## Step-by-Step Deployment to DigitalOcean + Cloudflare

### Phase 1: Setup Domain (5 minutes)

1. **Register domain on Cloudflare**
   ```
   https://www.cloudflare.com/products/registrar/
   → Search "sentriq.com"
   → $8.85/year
   → Complete checkout
   ```

2. **Cloudflare automatically becomes your DNS provider** (no extra steps!)

### Phase 2: Setup Server (15 minutes)

1. **Create DigitalOcean account**: https://www.digitalocean.com
2. **Create Droplet**:
   - Image: Ubuntu 22.04 LTS
   - Size: $5/month basic
   - Region: Choose nearest to you
3. **SSH into droplet**:
   ```bash
   ssh root@YOUR_DROPLET_IP
   ```

### Phase 3: Deploy Application (30 minutes)

1. **Install Docker**:
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sh get-docker.sh
   ```

2. **Clone your GitHub repo**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/openbb_platform.git
   cd openbb_platform
   ```

3. **Create Dockerfile**:
   ```dockerfile
   FROM python:3.14-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install -r requirements.txt
   COPY . .
   EXPOSE 8000 8501
   CMD ["bash", "start_all.sh"]
   ```

4. **Build and run**:
   ```bash
   docker build -t openbb-app .
   docker run -d -p 8000:8000 -p 8501:8501 openbb-app
   ```

### Phase 4: Connect Domain (10 minutes)

1. **In Cloudflare Dashboard**:
   - Go to your domain (sentriq.com)
   - DNS → Records
   - Add A record:
     ```
     Name: @
     Type: A
     Content: YOUR_DROPLET_IP
     TTL: Auto
     ```

2. **Enable HTTPS** (automatic with Cloudflare):
   - SSL/TLS → Overview
   - Choose "Flexible" or "Full"

3. **Wait 10-15 minutes** for DNS propagation

4. **Access your app**:
   ```
   https://sentriq.com (your domain!)
   ```

---

## Environment Variables for Deployment

Create `.env` in deployment server:

```bash
# API Keys (get from respective services)
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...
FRED_API_KEY=...
TIINGO_API_KEY=...

# FastAPI
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
FASTAPI_DEBUG=false

# Streamlit
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_HEADLESS=true

# Frontend
FRONTEND_URL=https://sentriq.com
API_URL=https://api.sentriq.com

# Security
SECRET_KEY=your-secret-key-here-minimum-32-chars
DATABASE_URL=postgresql://user:pass@localhost/dbname

# Feature Flags
ENABLE_AI_INSIGHTS=true
ENABLE_TRADING_ENGINE=true
DEBUG_MODE=false
```

---

## Docker Compose for Easy Local + Production

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  fastapi:
    build: .
    ports:
      - "8000:8000"
    environment:
      - FASTAPI_HOST=0.0.0.0
      - FASTAPI_PORT=8000
    volumes:
      - .:/app
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

  streamlit:
    build: .
    ports:
      - "8501:8501"
    environment:
      - STREAMLIT_SERVER_PORT=8501
    volumes:
      - .:/app
    command: streamlit run app.py --server.port 8501 --logger.level=debug

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - fastapi
      - streamlit
```

---

## Integration with Claude AI API

Since you use Claude Copilot:

```python
# api/routes/ai_insights.py
from anthropic import Anthropic

client = Anthropic()

@router.post("/ai-insights")
def get_ai_insights(query: str, market_data: dict):
    """Use Claude to analyze market data and provide insights"""
    
    prompt = f"""
    Analyze this trading data: {market_data}
    User query: {query}
    Provide actionable insights for a trader.
    """
    
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return {"insights": response.content[0].text}
```

---

## Monitoring & Maintenance

### Logs
```bash
# On Docker
docker logs container_id -f

# On VPS
tail -f /var/log/openbb-app/fastapi.log
tail -f /var/log/openbb-app/streamlit.log
```

### Updates
```bash
cd ~/openbb_platform
git pull origin main
docker rebuild .
docker restart container_id
```

### Health Checks
```bash
# FastAPI health
curl https://sentriq.com/api/health

# Streamlit
curl https://sentriq.com/_stcore/health
```

---

## Cost Breakdown (Monthly)

| Component | Cost |
|-----------|------|
| Domain (.com on Cloudflare) | $0.74 |
| VPS (DigitalOcean $5 droplet) | $5.00 |
| Database (PostgreSQL add-on) | $7.00 |
| SSL Certificate (Cloudflare free) | $0.00 |
| **Total** | **~$12.74/month** |

---

## Next Steps

1. **This week**: Register domain on Cloudflare ($8.85)
2. **Next week**: Setup DigitalOcean droplet ($5/month)
3. **Following week**: Deploy your app
4. **Ongoing**: Monitor, update, scale as needed

---

**Questions about deployment?**
- Check DigitalOcean docs: https://docs.digitalocean.com
- Cloudflare support: https://support.cloudflare.com
- Your project GitHub issues

**Last Updated**: April 15, 2026
