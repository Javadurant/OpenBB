# 🌐 DOMAIN REGISTRATION GUIDE FOR SENTRIQ PROJECT

## Quick TL;DR

| Item | Recommendation | Cost | Time |
|------|---|---|---|
| **Domain** | `sentriq.com` on Cloudflare | $8.85/year | 5 min |
| **VPS** | DigitalOcean $5/month | $5/month | 10 min |
| **Total** | Full production setup | $12.74/month | 30 min |

---

## Step 1: Choose Your Domain Name (5 minutes)

### Recommended Names (in order of preference)

**🥇 Tier 1: Most Professional**
- `sentriq.com` - Your brand, memorable ⭐ BEST
- `sentriqai.com` - Emphasizes AI component
- `sentriq.io` - Tech-forward alternative ($15/year)

**🥈 Tier 2: Descriptive**
- `tradesentriq.com` - Clear purpose
- `sentriqtrade.com` - Action-oriented
- `sentriq.co` - Short, professional ($10/year)

**🥉 Tier 3: Broader Appeal**
- `tradeit.ai` - Simple, modern
- `aitrader.app` - Technology-focused
- `financialai.io` - Descriptive

### Check Availability

1. **Cloudflare Registrar**: https://www.cloudflare.com/products/registrar/
2. **Namecheap**: https://www.namecheap.com
3. **Google Domains (Squarespace)**: https://domains.google.com

Search your chosen name and see what's available.

---

## Step 2: Register Domain on Cloudflare (5 minutes)

### Why Cloudflare?
- **Cheapest**: $8.85/year (at-cost pricing, no markup)
- **Best Security**: Free DDoS protection for API
- **Free SSL/HTTPS**: Automatic SSL from day 1
- **Free Email Forwarding**: hello@sentriq.com → your-email@gmail.com
- **API Management**: Perfect for your FastAPI backend

### Registration Steps

1. **Visit Cloudflare Registrar**
   ```
   https://www.cloudflare.com/products/registrar/
   ```

2. **Search your domain**
   - Example: Search for "sentriq.com"
   - Shows: Available for $8.85/year ✅

3. **Add to Cart**
   - Quantity: 1 year
   - Auto-renew: Yes (to avoid expiration)

4. **Checkout**
   - Create/Login to Cloudflare account
   - Add payment method
   - Complete purchase

5. **DNS Setup**
   - Cloudflare automatically becomes your DNS provider
   - No additional configuration needed!

### After Registration

Your domain point to:
- Cloudflare nameservers (automatic)
- Your VPS IP address later (see VPS setup)
- SSL certificate (automatic)

---

## Step 3: Verify Domain Ownership

After registration (2-5 minutes later):

1. **Login to Cloudflare Dashboard**
2. **Select your domain** (sentriq.com)
3. **DNS Tab** → Should show:
   ```
   Status: ACTIVE ✅
   Nameservers: cloudflare.com
   ```

4. **Verify** the domain is working:
   ```bash
   dig sentriq.com
   # Should show Cloudflare nameservers
   ```

---

## Step 4: Setup to Point to Your Website

### Phase A: During Development (localhost)
No setup needed! Your domain points to Cloudflare's servers.

### Phase B: When Ready to Deploy

**Connect to your VPS:**

1. **Create DigitalOcean account**: https://www.digitalocean.com
2. **Create a Droplet** ($5/month, Ubuntu 22.04)
3. **Get your Droplet's IP address** (e.g., 123.45.67.89)
4. **In Cloudflare Dashboard**:
   - DNS → Records
   - Add A Record:
     ```
     Name: @
     Type: A
     Content: 123.45.67.89 (your droplet IP)
     TTL: Auto
     Orange cloud icon: Click to enable proxy
     ```
5. **Wait 10-15 minutes** for DNS propagation

6. **Verify**:
   ```bash
   dig sentriq.com
   # Should resolve to 123.45.67.89
   ```

---

## Step 5: SSL/HTTPS Setup (Automatic!)

Cloudflare handles SSL automatically:

1. **SSL/TLS Mode**:
   - Login to Cloudflare Dashboard
   - SSL/TLS → Overview
   - Select: "Flexible" or "Full"

2. **HTTPS Redirect**:
   - SSL/TLS → Edge Certificates
   - Enable "Always Use HTTPS"

3. **Result**: 
   - http://sentriq.com → https://sentriq.com ✅
   - Certificate auto-renews ✅

---

## Domain Registrar Comparison

### Recommended: Cloudflare Registrar ⭐

| Metric | Price |
|--------|-------|
| .com Registration | $8.85/year |
| Renewal | $8.85/year (guaranteed) |
| Privacy | Free |
| Email Forwarding | Free |
| DNS Management | Free |
| SSL Certificate | Free |
| DDoS Protection | Free |

**Cloudflare Pros**:
- Cheapest pricing
- Integrated DNS for API management
- Security for financial data

### Alternative: Namecheap

| Metric | Price |
|--------|-------|
| .com Registration | $8.98/year |
| Renewal | $10.98/year |
| Privacy | $2.78/year |
| Email Forwarding | Free |
| DNS Management | Free |
| SSL Certificate | $9/year (or free Let's Encrypt) |

**Namecheap Pros**:
- Good customer support
- Simple interface
- Affordable

### Alternative: Google Domains (Squarespace)

| Metric | Price |
|--------|-------|
| .com Registration | $12/year |
| Renewal | $12/year |
| Privacy | Included |
| Email Forwarding | Free |
| DNS Management | Free |
| SSL Certificate | $10/year (or free Let's Encrypt) |

**Google Domains Pros**:
- Integrated with Google services
- Simple setup
- Reliable

---

## Complete Checklist: From Domain to Live Website

```
Week 1:
☐ Choose domain name (sentriq.com)
☐ Register on Cloudflare ($8.85, takes 5 min)
☐ Verify domain is active (DNS ✅)

Week 2-3:
☐ Create DigitalOcean account ($5/month)
☐ Create Droplet (Ubuntu 22.04)
☐ Get droplet IP address

Week 3:
☐ Update Cloudflare DNS to point to droplet IP
☐ Setup SSL (automatic)
☐ Verify https://sentriq.com works

Week 4+: LIVE! 🎉
☐ Your website is on sentriq.com
☐ All services accessible at:
   - https://sentriq.com (React frontend)
   - https://api.sentriq.com (FastAPI - optional subdomain)
   - https://dashboard.sentriq.com (Streamlit - optional)
```

---

## Advanced: Email Setup with Your Domain

### Setup Email Forwarding (Free)

1. **In Cloudflare Dashboard**:
   - Email Routing
   - Create Route:
     ```
     catch-all: hello@sentriq.com
     forward to: your-personal-email@gmail.com
     ```

2. **Result**: 
   ```
   info@sentriq.com → your-email@gmail.com ✅
   support@sentriq.com → your-email@gmail.com ✅
   ```

### Full Email Setup (Optional, $15-20/month)

Use your domain for sending emails:

1. **Mailgun API**: https://www.mailgun.com
   ```python
   # Send email from hello@sentriq.com
   from mailgun import Mailgun
   mg = Mailgun('mg.sentriq.com', 'key_xxxx')
   mg.send_email('trades@sentriq.com', ['info@sentriq.com'], 
                 subject='Trading Signal', text='...')
   ```

2. **SendGrid**: https://sendgrid.com (similar)

3. **Transactional Email**: SendGrid, Mailgun, AWS SES

---

## Subdomain Setup (Optional)

After main domain works, create subdomains:

```bash
# In Cloudflare DNS:

@ (root)          → 123.45.67.89    (React frontend)
api.sentriq.com   → 123.45.67.89    (FastAPI backend)
dashboard.sentriq.com → 123.45.67.89 (Streamlit dashboard)
admin.sentriq.com → 123.45.67.89    (Admin panel)
```

Then in your VPS (Nginx):
```nginx
server {
    server_name sentriq.com;
    location / { proxy_pass http://localhost:5173; }
}

server {
    server_name api.sentriq.com;
    location / { proxy_pass http://localhost:8000; }
}

server {
    server_name dashboard.sentriq.com;
    location / { proxy_pass http://localhost:8501; }
}
```

---

## Integration with Your Claude Copilot

Since you use Claude:

1. **Add API Configuration to .env**:
   ```bash
   OPENAI_API_KEY=sk-your-key
   # Claude connections via FastAPI
   ```

2. **Claude can help with**:
   - Domain strategy
   - Architecture decisions
   - API endpoint design
   - Deployment automation

3. **Ask Claude**:
   - "Generate Nginx config for sentriq.com"
   - "Create Docker setup for OpenBB + React"
   - "Optimize API response time"

---

## Quick Links

| Resource | URL |
|----------|-----|
| **Cloudflare Registrar** | https://www.cloudflare.com/products/registrar/ |
| **DigitalOcean** | https://www.digitalocean.com |
| **Namecheap** | https://www.namecheap.com |
| **Cloudflare DNS** | https://dash.cloudflare.com |
| **Check DNS** | https://mxtoolbox.com |
| **Verify SSL** | https://www.ssllabs.com/ssltest/ |

---

## Estimated Timeline

```
Day 1 (5 min):    Register domain on Cloudflare
Day 2-5:          Setup VPS on DigitalOcean (wait for setup)
Day 5-6 (15 min): Update Cloudflare DNS to point to VPS
Day 6-7 (1 hour): Deploy your app to VPS (see DEPLOYMENT.md)
Day 7:            Your website is LIVE on sentriq.com! 🎉
```

---

## FAQ

**Q: Can I change my mind about domain name?**
A: Yes! You can register multiple domains and point them all to the same IP. Keep sentriq.com as primary.

**Q: What if sentriq.com is taken?**
A: Try alternatives:
- sentriqai.com ($11/year)
- sentriq.io ($15/year)  
- tradesentriq.com
- sentriqtrade.com

**Q: Do I need a separate database domain?**
A: No. Database connects internally within your VPS.

**Q: How do I handle multiple locations (frontend, API, dashboard)?**
A: All live at same IP, use Nginx to proxy:
- sentriq.com → React (5173)
- api.sentriq.com → FastAPI (8000)
- dashboard.sentriq.com → Streamlit (8501)

**Q: Can Claude help manage my domain?**
A: Not directly, but Claude can:
- Help write deployment scripts
- Generate DNS configurations
- Suggest architecture improvements
- Write monitoring queries

---

## Next Action Items

1. **TODAY**: Go to https://www.cloudflare.com/products/registrar/
2. **TODAY**: Search "sentriq.com" (or your chosen name)
3. **TODAY**: Register for $8.85/year
4. **THIS WEEK**: Setup DigitalOcean droplet ($5/month)
5. **THIS WEEK**: Deploy your app (see DEPLOYMENT.md)

**Total investment**: ~$14/month for a professional .com domain with full stack deployment

---

**Questions?** Check DEPLOYMENT.md for VPS setup, or ARCHITECTURE.md for technical questions.

**Last Updated**: April 15, 2026
**Domain Strategy**: Cloudflare first, scale later
