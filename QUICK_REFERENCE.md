# ⚡ Quick Reference Card

## 🚀 Start Application

```bash
# Terminal 1 - Backend
cd backend && ./run_backend.sh

# Terminal 2 - Frontend  
cd frontend && ./run_frontend.sh
```

## 🔗 URLs

- **Web App**: http://localhost:5173
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## 📝 First Time Setup

```bash
# 1. Add API key
cp .env.example .env
# Edit .env with your GEMINI_API_KEY

# 2. Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Frontend setup
cd frontend
npm install

# 4. Add videos
cp your-match.mp4 videos/
```

## 🛠️ Common Commands

```bash
# Stop servers: Ctrl+C in each terminal

# Reinstall backend deps
cd backend && pip install -r requirements.txt

# Reinstall frontend deps
cd frontend && npm install

# Check backend health
curl http://localhost:8000/health

# List videos via API
curl http://localhost:8000/api/videos/list

# Build frontend for production
cd frontend && npm run build
```

## 📁 Key Files

- `.env` - Your API keys (NEVER commit!)
- `videos/` - Put your .mp4 files here
- `backend/src/app.py` - Backend entry point
- `frontend/src/App.tsx` - Frontend main component
- `backend/src/video_analysis/controller.py` - AI logic

## 🐛 Quick Fixes

```bash
# Port 8000 in use?
lsof -ti:8000 | xargs kill -9

# Port 5173 in use?
lsof -ti:5173 | xargs kill -9

# Backend won't start?
# - Check .env has GEMINI_API_KEY
# - Check venv is activated

# Frontend won't connect?
# - Check backend is running
# - Check frontend/.env has correct API URL
```

## 🎯 API Endpoints

### GET /api/videos/list
```bash
curl http://localhost:8000/api/videos/list
```

### POST /api/analyze
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"filename": "match.mp4"}'
```

## 📦 Tech Stack Summary

**Backend:**
- FastAPI (async Python web framework)
- Google Gemini 2.5 Flash (AI video analysis)
- Uvicorn (ASGI server)

**Frontend:**
- React 18 + TypeScript
- Vite (build tool)
- Ant Design (UI components)
- Axios (HTTP client)

## 🔐 Environment Variables

**Root .env:**
```bash
GEMINI_API_KEY=your_key_here
ELEVENLABS_API_KEY=your_key_here  # Optional
```

**frontend/.env:**
```bash
VITE_API_BASE_URL=http://localhost:8000/api
```

---

**For detailed docs, see [README.md](./README.md) and [SETUP_GUIDE.md](./SETUP_GUIDE.md)**

