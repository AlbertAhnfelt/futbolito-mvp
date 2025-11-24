import json
import time
import traceback
from pathlib import Path
from typing import Optional
from google import genai
from google.genai import types

from . import GEMINI_API_KEY, ELEVENLABS_API_KEY
from .audio.tts_generator import TTSGenerator
from .analysis.event_detector import EventDetector
from .commentary.commentary_generator import CommentaryGenerator
from .video.video_processor import VideoProcessor
from .video.time_utils import parse_time_to_seconds


# -------------------------------------------------------------------
# Multi-language helpers (EN / FR / ES)
# -------------------------------------------------------------------

SUPPORTED_LANGUAGES = {"en", "fr", "es"}

LANGUAGE_NAME = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
}


def _normalize_language(language: Optional[str]) -> str:
    """Normalize requested language code; fallback to 'en' if unsupported."""
    if not language:
        return "en"
    language = language.lower()
    if language not in SUPPORTED_LANGUAGES:
        return "en"
    return language


# -------------------------------------------------------------------
# TRANSLATION ADAPTED TO NEW FORMAT (Lead + Co)
# -------------------------------------------------------------------

def _translate_commentaries(client, commentaries, target_language: str):
    """
    Translate each commentary line (Lead and Co) into the target language.
    Mutates commentary.text in place.
    """
    if target_language == "en":
        return

    lang_name = LANGUAGE_NAME[target_language]
    print(f"\nStep 4 (optional): Translating commentary to {lang_name}...")

    for idx, commentary in enumerate(commentaries):
        print(f"  [{idx + 1}/{len(commentaries)}] Translating segment...")

        for line_obj in commentary.text:   # 🔄 MODIFIED
            original_line = line_obj.line

            prompt = f"""
You are a professional translator specializing in football (soccer) commentary.

Translate the following commentator line into {lang_name}.
- Preserve tone, intensity, football terminology.
- Keep player names, numbers, and times unchanged.
- Return ONLY the translated line.

Original:
\"\"\"{original_line}\"\"\""""

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[types.Part.from_text(prompt)],
            )

            translated_text = response.text.strip()
            line_obj.line = translated_text  # 🔄 MODIFIED


def list_videos():
    """List all MP4 files in the videos directory."""
    videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
    videos_dir.mkdir(exist_ok=True)
    return [f.name for f in videos_dir.glob('*.mp4')]


# -------------------------------------------------------------------
# MAIN PIPELINE
# -------------------------------------------------------------------

async def analyze_video(filename: str, language: str = "en"):
    """
    Complete video analysis pipeline with dual-commentator commentary.
    """
    try:
        print(f"\n{'='*60}")
        print("🎬 VIDEO ANALYSIS PIPELINE - TWO COMMENTATORS")
        print(f"{'='*60}\n")

        language = _normalize_language(language)
        print(f"Target commentary language: {LANGUAGE_NAME[language]} ({language})")

        # Init Gemini
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        client = genai.Client(api_key=GEMINI_API_KEY)

        # Video paths
        videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
        video_path = videos_dir / filename

        if not video_path.exists():
            raise FileNotFoundError(f"Video file {filename} not found")

        video_processor = VideoProcessor()

        # Step 1 — Ensure audio
        print("Step 1: Preparing video...")
        video_path_with_audio = video_processor.ensure_video_has_audio(video_path)
        video_duration = video_processor.get_video_duration(video_path_with_audio)

        # Step 2 — Upload to Gemini
        print("\nStep 2: Uploading video to Gemini...")
        uploaded_file = client.files.upload(file=str(video_path_with_audio))
        file_name = uploaded_file.name

        print("Waiting for processing...")
        for _ in range(60):
            file_info = client.files.get(name=file_name)
            if file_info.state.name == "ACTIVE":
                print("✓ File is ready!")
                break
            time.sleep(1)
        else:
            raise TimeoutError("File processing timeout")

        file_uri = uploaded_file.uri

        # Step 3 — Event detection
        print("\nStep 3: Event Detection")
        event_detector = EventDetector(api_key=GEMINI_API_KEY)
        events = event_detector.detect_events(
            file_uri=file_uri,
            duration_seconds=video_duration,
            interval_seconds=30
        )

        print(f"✓ Event detection complete — {len(events)} events")

        # Step 4 — Commentary generation
        print("\nStep 4: Commentary Generation (Two commentators)")
        commentary_generator = CommentaryGenerator(api_key=GEMINI_API_KEY)
        events_dict = [e.model_dump() for e in events]

        commentaries = commentary_generator.generate_commentary(
            events=events_dict,
            video_duration=video_duration,
            use_streaming=False
        )

        print(f"✓ Commentary generation complete — {len(commentaries)} segments")

        # Step 5 — OPTIONAL Translation
        _translate_commentaries(client, commentaries, language)

        # Step 6 — TTS Generation (ADAPTED)
        print("\nStep 5: TTS Audio Generation")

        commentaries_dict = []

        def merge_text_lines(lines):
            """Merge Lead + Co lines for a single TTS output."""
            return " ".join([l.line for l in lines])  # 🔄 MODIFIED

        if ELEVENLABS_API_KEY:
            try:
                tts_generator = TTSGenerator(
                    api_key=ELEVENLABS_API_KEY,
                    default_voice_id="nrD2uNU2IUYtedZegcGx"
                )

                for i, commentary in enumerate(commentaries):
                    merged_text = merge_text_lines(commentary.text)

                    print(f"  [{i+1}/{len(commentaries)}] Generating audio...")
                    print(f"    Text: {merged_text[:80]}...")

                    audio_base64 = tts_generator.generate_audio(merged_text)

                    commentary_dict = commentary.model_dump()
                    commentary_dict['audio_base64'] = audio_base64 or ""

                    commentaries_dict.append(commentary_dict)

                print("✓ TTS generation completed!")

            except Exception:
                print("[ERROR] TTS generation failed — using empty audio")
                for commentary in commentaries:
                    commentary_dict = commentary.model_dump()
                    commentary_dict['audio_base64'] = ""
                    commentaries_dict.append(commentary_dict)
        else:
            print("[WARN] No ELEVENLABS_API_KEY — skipping TTS")
            for commentary in commentaries:
                commentary_dict = commentary.model_dump()
                commentary_dict['audio_base64'] = ""
                commentaries_dict.append(commentary_dict)

        # Step 7 — Video Generation
        print("\nStep 6: Video Generation (with 1s audio delay)")
        output_filename = video_processor.generate_commentary_video(
            video_path=video_path,
            commentaries=commentaries_dict
        )

        print("\n✓ VIDEO ANALYSIS COMPLETED SUCCESSFULLY!")
        print(f"Generated video: {output_filename}")

        # Build highlights for frontend
        highlights = []
        for c in commentaries_dict:

            start_secs = parse_time_to_seconds(c['start_time'])
            end_secs = parse_time_to_seconds(c['end_time'])

            events_in_range = [
                e for e in events
                if start_secs <= parse_time_to_seconds(e.time) <= end_secs
            ]

            avg_intensity = (
                sum(e.intensity for e in events_in_range) / len(events_in_range)
                if events_in_range else 5
            )

            merged_text = "\n".join([line["line"] for line in c["text"]])  # 🔄 MODIFIED

            highlight = {
                "start_time": c["start_time"],
                "end_time": c["end_time"],
                "commentary": merged_text,
                "intensity": int(avg_intensity),
                "audio_base64": c.get("audio_base64", "")
            }

            highlights.append(highlight)

        return {
            "events": [e.model_dump() for e in events],
            "commentaries": [c.model_dump() for c in commentaries],
            "highlights": highlights,
            "generated_video": output_filename
        }

    except Exception as e:
        print("=" * 60)
        print("ERROR in analyze_video:")
        print(traceback.format_exc())
        print("=" * 60)
        raise
