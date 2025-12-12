# Deployment Guide

## Prerequisites

- Node.js and npm installed
- Cloudflare account (free tier)
- Wrangler CLI: `npm install -g wrangler`

## Step 1: Deploy Worker

```bash
cd worker

# Login to Cloudflare (first time only)
npx wrangler login

# Deploy worker
npx wrangler deploy

# Note the worker URL (e.g., https://cw-studio-relay.your-subdomain.workers.dev)
```

## Step 2: Update Frontend Configuration

Edit `public/js/landing.js` and `public/js/room-controller.js`:

```javascript
const WORKER_URL = 'wss://cw-studio-relay.YOUR-SUBDOMAIN.workers.dev';
```

Replace `YOUR-SUBDOMAIN` with your actual Cloudflare Workers subdomain.

## Step 3: Deploy Frontend to Cloudflare Pages

```bash
cd ..

# Deploy to Pages
npx wrangler pages deploy public/ --project-name=cw-studio-tcp

# Your site will be at: https://cw-studio-tcp.pages.dev
```

## Step 4: Test Locally

### Terminal 1: Start Worker
```bash
cd worker
npx wrangler dev
```

### Terminal 2: Serve Frontend
```bash
cd public
python3 -m http.server 8000
```

### Open Browser
```
http://localhost:8000/index.html
```

## Configuration

**Worker URL** in frontend files:
- Local: `ws://localhost:8787`
- Production: `wss://your-worker.workers.dev`

**CORS:** Worker allows all origins by default (development). For production, configure in `worker/src/index.js`.

## Custom Domain (Optional)

1. Add domain to Cloudflare
2. Update `worker/wrangler.toml`:
   ```toml
   routes = [
     { pattern = "cw-relay.yourdomain.com", zone_name = "yourdomain.com" }
   ]
   ```
3. Redeploy: `wrangler deploy`

## Troubleshooting

**Worker not connecting:**
- Check worker is deployed: `npx wrangler whoami`
- Verify URL in frontend matches worker URL
- Check browser console for errors

**CORS errors:**
- Worker should return proper headers (already configured)

**Audio not working:**
- User interaction required (click anywhere first)
- Check browser audio permissions
