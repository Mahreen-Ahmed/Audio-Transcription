import time
import tempfile
from pathlib import Path
import whisper
import numpy as np
import asyncio

from app.core.config import settings
from app.services.storage import storage_service

# Load model once at startup (expensive operation)
_model = None


def get_model():
    global _model
    if _model is None:
        print(f"Loading Whisper model: {settings.WHISPER_MODEL}")
        _model = whisper.load_model(settings.WHISPER_MODEL)
        print("Whisper model loaded successfully")
    return _model


def transcribe_audio(audio_path: str) -> dict:
    """
    Transcribe audio file using OpenAI Whisper.
    Supports both local files and Supabase Storage paths.

    Returns dict with:
        - text: full transcript
        - language: detected language code
        - duration: audio duration in seconds
        - segments: list of timed segments
    """
    model = get_model()
    
    temp_file = None
    actual_audio_path = audio_path
    
    # Handle Supabase paths by downloading to temp file
    if audio_path.startswith("supabase://"):
        try:
            # Create temp file with appropriate extension
            ext = audio_path.rsplit(".", 1)[-1].lower() if "." in audio_path else "wav"
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}")
            temp_file.close()
            
            # Get audio content
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            audio_content = loop.run_until_complete(storage_service.get_audio(audio_path))
            loop.close()
            
            # Write to temp file
            with open(temp_file.name, "wb") as f:
                f.write(audio_content)
            
            actual_audio_path = temp_file.name
        except Exception as e:
            print(f"Error downloading from Supabase: {e}")
            if temp_file:
                Path(temp_file.name).unlink(missing_ok=True)
            raise

    start = time.time()
    result = model.transcribe(
        actual_audio_path,
        verbose=False,
        fp16=False,
        no_speech_threshold=0.6,
        condition_on_previous_text=False
    )
    elapsed = time.time() - start

    # Get audio duration from segments
    duration = result["segments"][-1]["end"] if result["segments"] else 0.0

    print(f"Transcription completed in {elapsed:.2f}s for {audio_path}")
    
    # Clean up temp file
    if temp_file:
        Path(temp_file.name).unlink(missing_ok=True)

    return {
        "text": result["text"].strip(),
        "language": result["language"],
        "duration_seconds": duration,
        "segments": result["segments"],
    }
