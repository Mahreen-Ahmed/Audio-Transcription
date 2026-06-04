import time
import whisper
import numpy as np

from app.core.config import settings

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

    Returns dict with:
        - text: full transcript
        - language: detected language code
        - duration: audio duration in seconds
        - segments: list of timed segments
    """
    model = get_model()

    start = time.time()
    result = model.transcribe(
        audio_path,
        verbose=False,
        fp16=False,
    )
    elapsed = time.time() - start

    # Get audio duration from segments
    duration = result["segments"][-1]["end"] if result["segments"] else 0.0

    print(f"Transcription completed in {elapsed:.2f}s for {audio_path}")

    return {
        "text": result["text"].strip(),
        "language": result["language"],
        "duration_seconds": duration,
        "segments": result["segments"],
    }
