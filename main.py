import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Initialize Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# Define highlight schema
class highlight(BaseModel):
    start_time: str
    end_time: str
    description: str

# Analyze video with Gemini
response = client.models.generate_content(
    model='models/gemini-2.5-flash',
    contents=types.Content(
        parts=[
            types.Part(
                file_data=types.FileData(file_uri='https://www.youtube.com/watch?v=AlnHNi0hdO0')
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

print("Response text:")
print(response.text)

# Parse JSON response
my_dict = json.loads(response.text)
print("\nParsed highlights:")
print(my_dict)

# Create output folder if it doesn't exist
output_folder = "output"
os.makedirs(output_folder, exist_ok=True)

# Save JSON to output folder
output_file = os.path.join(output_folder, "highlights.json")
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(my_dict, f, indent=2, ensure_ascii=False)

print(f"\nJSON saved to: {output_file}")

# Generate audio narration with ElevenLabs
#elevenlabs = ElevenLabs(api_key=ELEVENLABS_API_KEY)
#
#audio = elevenlabs.text_to_speech.convert(
#    text=my_dict[1]["description"],
#    voice_id="JBFqnCBsd6RMkjVDRZzb",
#    model_id="eleven_multilingual_v2",
#    output_format="mp3_44100_128",
#)

#play(audio)