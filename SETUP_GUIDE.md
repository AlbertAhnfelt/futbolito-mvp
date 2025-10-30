# 🚀 Futbolito MVP - Quick Setup Guide

This guide will help you get the application running in under 5 minutes!

## ✅ Prerequisites Check

Before starting, make sure you have:

- [ ] Python 3.9 or higher (`python --version`)
- [ ] Node.js 20 or higher (`node --version`)
- [ ] A Google Gemini API key ([Get one here](https://ai.google.dev/))
- [ ] An ElevenLabs API key (for text-to-speech) ([Get one here](https://elevenlabs.io/))

**Note:** FFmpeg is automatically installed with the Python dependencies - no manual installation needed!

## 📝 Step-by-Step Setup

### 1️⃣ Configure API Keys (REQUIRED)

```bash
# Copy the environment template
cp .env.example .env

# Edit .env and replace 'your_gemini_api_key_here' with your actual key
# On Mac/Linux:
nano .env
# Or use any text editor
```

Your `.env` should look like:
```
GEMINI_API_KEY=AIzaSy...your_actual_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
```

### 2️⃣ Setup Backend

```bash
cd backend

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Make run script executable (Mac/Linux only)
chmod +x run_backend.sh
```

### 3️⃣ Setup Frontend

```bash
cd frontend  # From project root

# Install dependencies
npm install

# Make run script executable (Mac/Linux only)
chmod +x run_frontend.sh
```

### 4️⃣ Add Video Files

```bash
# Place your .mp4 football match videos in the videos folder
cp /path/to/your/match.mp4 videos/
```

## 🎮 Running the Application

### Option A: Using Run Scripts (Recommended - Mac/Linux)

**Terminal 1 - Backend:**
```bash
cd backend
./run_backend.sh
```

**Terminal 2 - Frontend:**
```bash
cd frontend
./run_frontend.sh
```

### Option B: Manual Start (All Platforms)

**Terminal 1 - Backend:**
```bash
cd backend
source venv/bin/activate  # Windows: venv\Scripts\activate
cd src
python app.py
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

## 🌐 Access the Application

Once both servers are running:

- **Frontend (Web App)**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## 🎯 First Use

1. Open http://localhost:5173 in your browser
2. You'll see a dropdown with your available videos
3. Select a video from the list
4. Click "Analyze Video"
5. Wait 30-60 seconds for AI analysis
6. View the extracted highlights in the table!
7. A new video with AI-generated commentary will be saved to `videos/generated-videos/`

## 🐛 Common Issues

### "No videos found"
- Make sure you've added .mp4 files to the `videos/` folder
- The folder should be at the root: `futbolito-mvp/videos/`

### "Backend connection failed"
- Check that the backend is running on port 8000
- Verify your `GEMINI_API_KEY` is set correctly in `.env`
- Look at the backend terminal for error messages

### "Analysis failed"
- Ensure your Gemini API key is valid and has credits
- Check that the video file is not corrupted
- Video must be in MP4 format
- If you get FFmpeg errors, make sure `pip install -r requirements.txt` completed successfully

### Port already in use
**Backend (port 8000):**
```bash
# Find and kill process on port 8000
lsof -ti:8000 | xargs kill -9
```

**Frontend (port 5173):**
```bash
# Find and kill process on port 5173
lsof -ti:5173 | xargs kill -9
```

## 📦 Project Structure

```
futbolito-mvp/
├── backend/           # FastAPI backend
│   ├── src/
│   │   ├── app.py
│   │   └── video_analysis/
│   └── requirements.txt
├── frontend/          # React frontend
│   ├── src/
│   │   ├── App.tsx
│   │   ├── services/
│   │   └── types/
│   └── package.json
├── videos/            # Your .mp4 files go here
│   └── generated-videos/  # AI-generated commentary videos
└── .env              # Your API keys (don't commit!)
```

## 🔄 Stopping the Application

Press `Ctrl+C` in each terminal window to stop the servers.

## 🎓 Next Steps

- Read the main [README.md](./README.md) for detailed documentation
- Check out the API docs at http://localhost:8000/docs
- Explore the code in `backend/src/` and `frontend/src/`
- Add more videos and experiment!

## 💡 Tips

1. **Video Format**: Only MP4 files are supported
2. **Video Length**: Shorter videos (< 5 minutes) analyze faster
3. **API Limits**: Gemini API has rate limits - avoid analyzing too many videos rapidly
4. **Development**: Both servers support hot reload - changes will auto-refresh
5. **FFmpeg**: Automatically bundled with the Python dependencies - works on all platforms!

## 🤝 Need Help?

If you encounter issues not covered here:
1. Check the terminal logs for detailed error messages
2. Verify all prerequisites are installed
3. Ensure your API key is valid
4. Try the `/health` endpoint: http://localhost:8000/health

---

**Happy analyzing! ⚽️**

