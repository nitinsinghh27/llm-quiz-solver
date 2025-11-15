# Deployment Guide

This guide covers multiple deployment options for your LLM Quiz Solver.

## Prerequisites

Before deploying, ensure:
- ✅ Code works locally
- ✅ `.env` file is configured
- ✅ Test endpoint passes
- ✅ GitHub repository is ready

## Option 1: ngrok (Quick Testing - Recommended for Development)

### Installation

```bash
# macOS
brew install ngrok

# Or download from https://ngrok.com/download
```

### Setup

```bash
# Sign up at https://ngrok.com and get your auth token
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

### Deploy

```bash
# Start your Flask app
python app.py

# In another terminal, start ngrok
ngrok http 5001
```

### Result
You'll get a URL like: `https://abc123.ngrok.io`

**Pros**:
- ✅ Instant deployment
- ✅ Free tier available
- ✅ HTTPS included
- ✅ Great for testing

**Cons**:
- ❌ URL changes on restart (unless paid)
- ❌ Requires running on your machine
- ❌ Not suitable for production

---

## Option 2: Render.com (Recommended for Evaluation)

### Setup

1. **Push code to GitHub**:
   ```bash
   cd /Users/nitin/iitm-Projects/TDS/Project2
   git init
   git add .
   git commit -m "Initial commit: LLM Quiz Solver"
   git remote add origin YOUR_GITHUB_REPO_URL
   git push -u origin main
   ```

2. **Create Render account**: https://render.com

3. **Create New Web Service**:
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Configure:
     - **Name**: llm-quiz-solver
     - **Environment**: Python 3
     - **Build Command**:
       ```bash
       pip install -r requirements.txt && playwright install chromium && playwright install-deps
       ```
     - **Start Command**:
       ```bash
       gunicorn app:app --bind 0.0.0.0:$PORT --timeout 180 --workers 1
       ```
     - **Instance Type**: Free

4. **Add Environment Variables**:
   - Go to "Environment" tab
   - Add:
     - `SECRET`: your_secret
     - `EMAIL`: your_email@example.com
     - `AIPIPE_API_KEY`: your_aipipe_key
     - `AIPIPE_BASE_URL`: https://api.aipipe.ai/v1

5. **Deploy**: Click "Create Web Service"

### Result
You'll get: `https://llm-quiz-solver.onrender.com`

**Pros**:
- ✅ Free tier with 750 hours/month
- ✅ Auto-deploys from GitHub
- ✅ HTTPS included
- ✅ Persistent URL
- ✅ Good for production

**Cons**:
- ❌ Cold starts (spins down after inactivity)
- ❌ Slower build times
- ❌ Limited resources on free tier

---

## Option 3: Railway.app

### Setup

1. **Install Railway CLI**:
   ```bash
   npm i -g @railway/cli
   ```

2. **Login**:
   ```bash
   railway login
   ```

3. **Initialize and Deploy**:
   ```bash
   cd /Users/nitin/iitm-Projects/TDS/Project2
   railway init
   railway up
   ```

4. **Add Environment Variables**:
   ```bash
   railway variables set SECRET=your_secret
   railway variables set EMAIL=your_email@example.com
   railway variables set AIPIPE_API_KEY=your_aipipe_key
   railway variables set AIPIPE_BASE_URL=https://api.aipipe.ai/v1
   ```

5. **Get URL**:
   ```bash
   railway domain
   ```

**Pros**:
- ✅ Simple CLI deployment
- ✅ Free $5 credit monthly
- ✅ Fast deploys
- ✅ No cold starts

**Cons**:
- ❌ Credit-based (not unlimited free)
- ❌ Requires credit card after trial

---

## Option 4: Fly.io

### Setup

1. **Install Fly CLI**:
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login**:
   ```bash
   fly auth login
   ```

3. **Launch App**:
   ```bash
   cd /Users/nitin/iitm-Projects/TDS/Project2
   fly launch
   ```
   - Choose app name
   - Select region (Singapore for lowest latency)
   - Don't deploy yet

4. **Set Secrets**:
   ```bash
   fly secrets set SECRET=your_secret
   fly secrets set EMAIL=your_email@example.com
   fly secrets set AIPIPE_API_KEY=your_aipipe_key
   fly secrets set AIPIPE_BASE_URL=https://api.aipipe.ai/v1
   ```

5. **Create Dockerfile**:
   ```bash
   # Fly will create this automatically, but ensure it has:
   # - playwright installation
   # - chromium browser
   ```

6. **Deploy**:
   ```bash
   fly deploy
   ```

**Pros**:
- ✅ Good free tier
- ✅ Global edge network
- ✅ Docker-based (flexible)

**Cons**:
- ❌ More complex setup
- ❌ Docker knowledge helpful

---

## Recommended Deployment Strategy

### For Testing (Before Submission)
Use **ngrok**:
```bash
python app.py
ngrok http 5001
```

### For Google Form Submission
Use **Render.com**:
1. Free and reliable
2. Persistent URL
3. Auto-restart on errors
4. Easy setup

### Steps for Render Deployment

```bash
# 1. Create GitHub repo
cd /Users/nitin/iitm-Projects/TDS/Project2
git init
git add .
git commit -m "LLM Quiz Solver"

# 2. Push to GitHub
git remote add origin https://github.com/YOUR_USERNAME/llm-quiz-solver.git
git push -u origin main

# 3. Go to Render.com
# - Sign in with GitHub
# - New Web Service
# - Select your repo
# - Add environment variables
# - Deploy

# 4. Test your endpoint
curl https://your-app.onrender.com/health

# 5. Submit URL to Google Form
```

## Testing Your Deployment

```bash
# Health check
curl https://your-deployed-url.com/health

# Quiz test
curl -X POST https://your-deployed-url.com/quiz \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your_email@example.com",
    "secret": "your_secret",
    "url": "https://tds-llm-analysis.s-anand.net/demo"
  }'
```

## Troubleshooting

### Issue: Playwright fails to install
**Solution**: Ensure build command includes:
```bash
playwright install chromium && playwright install-deps
```

### Issue: Port binding error
**Solution**: Use `$PORT` environment variable:
```python
app.run(host='0.0.0.0', port=Config.PORT)
```

### Issue: Timeout on quiz solving
**Solution**: Increase timeout in gunicorn:
```bash
gunicorn app:app --timeout 180
```

### Issue: Cold start delays
**Solution**:
- Use Render's paid tier
- Or use Railway/Fly.io which have better cold start
- Or keep service warm with periodic pings

## Pre-Deployment Checklist

- [ ] Code tested locally
- [ ] `.env` configured correctly
- [ ] `test_endpoint.py` passes all tests
- [ ] Requirements.txt up to date
- [ ] GitHub repo is public
- [ ] MIT LICENSE added
- [ ] Environment variables ready
- [ ] Deployment platform account created
- [ ] URL obtained and working
- [ ] Health endpoint responds
- [ ] Demo quiz test successful

## Google Form Submission

Once deployed, submit to the Google Form:
1. **Email**: Your student email
2. **Secret**: Your secret string
3. **System Prompt**: From PROMPTS.md (max 100 chars)
4. **User Prompt**: From PROMPTS.md (max 100 chars)
5. **API Endpoint URL**: Your deployed HTTPS URL
6. **GitHub Repo URL**: Your public repository

## Monitoring

### Check Logs (Render)
```bash
# Via dashboard: Logs tab
# Shows real-time output
```

### Check Logs (Railway)
```bash
railway logs
```

### Check Logs (Fly)
```bash
fly logs
```

## Cost Estimate

| Platform | Free Tier | Monthly Cost |
|----------|-----------|--------------|
| ngrok | Limited | $0-8 |
| Render | 750 hrs | $0 |
| Railway | $5 credit | $0-5 |
| Fly.io | 3 VMs | $0 |

**Recommendation**: Start with Render.com free tier.

## Need Help?

1. Check server logs for errors
2. Test locally first with `python app.py`
3. Verify environment variables are set
4. Ensure GitHub repo is public
5. Check deployment platform docs
