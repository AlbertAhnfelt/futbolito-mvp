import os
import json
import time
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from parent directory
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)
CORS(app)

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# Define highlight schema
class highlight(BaseModel):
    start_time: str
    end_time: str
    description: str

@app.route('/videos/list', methods=['GET'])
def list_videos():
    try:
        videos_dir = Path(__file__).parent.parent / 'videos'
        videos_dir.mkdir(exist_ok=True)  # Create if doesn't exist

        # Get all MP4 files
        video_files = [f.name for f in videos_dir.glob('*.mp4')]
        return jsonify(video_files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analyze', methods=['POST'])
def analyze_video():
    try:
        data = request.json
        filename = data.get('filename')

        if not filename:
            return jsonify({'error': 'No filename provided'}), 400

        # Get video path from videos folder
        videos_dir = Path(__file__).parent.parent / 'videos'
        video_path = videos_dir / filename

        if not video_path.exists():
            return jsonify({'error': f'Video file {filename} not found'}), 404

        # Upload video to Gemini File API
        uploaded_file = client.files.upload(file=str(video_path))
        file_name = uploaded_file.name

        # Wait for file to be processed and become ACTIVE
        print(f"Uploaded file {file_name}, waiting for processing...")
        max_retries = 60  # Wait up to 60 seconds
        retry_count = 0

        while retry_count < max_retries:
            file_info = client.files.get(name=file_name)

            if file_info.state.name == "ACTIVE":
                print(f"File {file_name} is ready for analysis!")
                break

            print(f"File state: {file_info.state.name}. Waiting...")
            time.sleep(1)
            retry_count += 1

        if retry_count == max_retries:
            return jsonify({'error': 'File processing timeout'}), 500

        file_uri = uploaded_file.uri

        # Analyze video with Gemini
        response = client.models.generate_content(
            model='models/gemini-2.5-flash',
            contents=types.Content(
                parts=[
                    types.Part(
                        file_data=types.FileData(file_uri=file_uri)
                    ),
                    types.Part(text="""
                    Here is a short clip of a football match. Identify important events in the video.

                    IMPORTANT: Analyze ONLY the visual content of the video. DO NOT use any audio, commentary, or sound from the video.
                    Base your analysis purely on what you can see: player movements, ball trajectory, tackles, passes, shots, celebrations, etc.

                    For each event explain what happens in the video based solely on visual observation.
                    Only identify players if you can visually recognize them (jersey numbers, physical appearance, playing style).
                    Describe precisely what happened with football technical language based on visual analysis only.

                    For each highlight return a json with this format :
                    {
                      start_time : "00:00:00",
                      end_time : "00:00:00",
                      description : "XXX",
                    }

                    DO NOT RETURN ANY OTHER TEXT.
                    """)
                ]
            ),
            config={
                "response_mime_type": "application/json",
                "response_schema": list[highlight],
            },
        )

        # Parse JSON response
        highlights = json.loads(response.text)
        return jsonify(highlights)

    except Exception as e:
        print("=" * 50)
        print("ERROR in /analyze endpoint:")
        print(traceback.format_exc())
        print("=" * 50)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
