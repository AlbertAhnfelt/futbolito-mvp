# Futbolito MVP - Football Highlights Analyzer

An AI-powered web application that analyzes football match videos and automatically extracts key highlights using Google's Gemini AI.

## 🏗️ Architecture

This is a modern monorepo with:
- **Backend**: FastAPI (Python) - High-performance async API
- **Frontend**: React + TypeScript + Vite + Ant Design - Modern, responsive UI
- **AI**: Google Gemini 2.5 Flash for video analysis

## 📁 Project Structure

```
futbolito-mvp/
├── backend/              # FastAPI backend
│   ├── src/
│   │   ├── app.py                    # Main FastAPI application
│   │   └── video_analysis/           # Video analysis module
│   │       ├── __init__.py           # Environment setup
│   │       ├── route.py              # API endpoints
│   │       ├── controller.py         # Business logic
│   │       └── util.py               # Helper functions
│   └── requirements.txt  # Python dependencies
├── frontend/             # React frontend
│   ├── src/
│   │   ├── App.tsx                   # Main component
│   │   ├── services/api.ts           # API client
│   │   └── types/index.ts            # TypeScript types
│   ├── package.json      # Node dependencies
│   └── vite.config.ts    # Vite configuration
├── videos/               # Place your .mp4 files here
├── .env                  # Environment variables (not in git)
└── .env.example          # Environment template
```

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Node.js 20+
- npm or yarn
- Google Gemini API key ([Get one here](https://ai.google.dev/))

### 1. Clone and Setup Environment

```bash
cd futbolito-mvp

# Copy and configure environment variables
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 2. Backend Setup

```bash
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the backend server
cd src
python app.py
```

Backend will be available at: `http://localhost:8000`
- API Documentation: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

### 3. Frontend Setup

```bash
# In a new terminal, navigate to frontend
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend will be available at: `http://localhost:5173`

### 4. Add Videos

Place your football match videos (`.mp4` format) in the `videos/` folder at the root of the project.

```bash
mkdir -p videos
# Copy your .mp4 files to videos/
```

## 🎯 Usage

1. **Start both servers** (backend on port 8000, frontend on port 5173)
2. **Open your browser** to `http://localhost:5173`
3. **Select a video** from the dropdown (videos from the `videos/` folder)
4. **Click "Analyze Video"** and wait for AI analysis (may take 30-60 seconds)
5. **View highlights** in a beautiful table format

## 🔧 Configuration

### Backend Configuration

Edit `.env` in the project root:

```bash
# Required
GEMINI_API_KEY=your_gemini_api_key_here

# Optional (for future features)
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
```

### Frontend Configuration

Edit `frontend/.env`:

```bash
# API endpoint (default for local development)
VITE_API_BASE_URL=http://localhost:8000/api
```

## 📡 API Endpoints

### `GET /api/videos/list`
List all available videos in the `videos/` folder.

**Response:**
```json
["match1.mp4", "match2.mp4"]
```

### `POST /api/analyze`
Analyze a video and extract highlights.

**Request:**
```json
{
  "filename": "match1.mp4"
}
```

**Response:**
```json
[
  {
    "start_time": "00:00:15",
    "end_time": "00:00:25",
    "description": "Excellent through pass from midfielder, striker makes a run..."
  }
]
```

## 🛠️ Development

### Backend Development

```bash
cd backend/src
python app.py  # Auto-reload enabled
```

### Frontend Development

```bash
cd frontend
npm run dev  # Hot module reload enabled
```

### Building for Production

```bash
# Frontend
cd frontend
npm run build
npm run preview

# Backend - use production ASGI server
cd backend
pip install gunicorn
gunicorn src.app:app -w 4 -k uvicorn.workers.UvicornWorker
```

## 🧪 Testing

### Test Backend

```bash
cd backend
# Activate venv first
pytest  # (after installing pytest)

# Or test endpoints manually
curl http://localhost:8000/health
curl http://localhost:8000/api/videos/list
```

### Test Frontend

```bash
cd frontend
npm run test  # (after setting up tests)
```

## 📚 Tech Stack

### Backend
- **FastAPI** - Modern, fast web framework
- **Uvicorn** - ASGI server
- **Google Gemini AI** - Video analysis
- **Pydantic** - Data validation
- **Python-dotenv** - Environment management

### Frontend
- **React 18** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool
- **Ant Design** - UI components
- **Axios** - HTTP client

## 🤝 Team

Team 7: Jayden Caixing Piao, Salah Eddine Nifa, Albert Ahnfelt, Antoine Fauve, Lucas Rulland, Hyun Suk Kim

## 📝 License

MIT License - feel free to use this project for learning and development!

## 🚧 Future Enhancements

- [ ] Video upload via UI
- [ ] Audio narration with ElevenLabs
- [ ] Highlight video clips export
- [ ] Multi-language support
- [ ] User authentication
- [ ] Video player integration
- [ ] Real-time analysis progress
- [ ] Docker containerization

## 🐛 Troubleshooting

### Backend won't start
- Check if port 8000 is available
- Verify `GEMINI_API_KEY` is set in `.env`
- Ensure Python 3.9+ is installed

### Frontend won't connect to backend
- Check backend is running on port 8000
- Verify `VITE_API_BASE_URL` in `frontend/.env`
- Check browser console for CORS errors

### No videos showing
- Ensure `.mp4` files are in `videos/` folder
- Check file permissions
- Verify backend has access to videos folder

### Analysis fails
- Verify Gemini API key is valid
- Check video file is not corrupted
- Ensure video is in MP4 format
- Check backend logs for detailed errors

