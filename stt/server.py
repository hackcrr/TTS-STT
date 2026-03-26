#!/usr/bin/env python3
"""Flask backend for speech-to-text using Whisper."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
import whisper
from flask import Flask, jsonify, request
from flask_cors import CORS

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from env_utils import env_int, load_env_files

load_env_files(ROOT_DIR)

FFMPEG_DIR = os.environ.get(
    "FFMPEG_DIR",
    r"C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links",
)
if FFMPEG_DIR and Path(FFMPEG_DIR).exists():
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
DEFAULT_LANGUAGE = os.environ.get("WHISPER_LANG", "en")
STT_HOST = os.environ.get("STT_HOST", "0.0.0.0")
STT_PORT = env_int("STT_PORT", 5001)
DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"

app = Flask(__name__)
CORS(app)

print(f"Loading Whisper model: {MODEL_SIZE}")
model = whisper.load_model(MODEL_SIZE)
print("Whisper model loaded.")


def normalize_language(language: str | None) -> str | None:
    value = (language or DEFAULT_LANGUAGE or "").strip().lower()
    return value or None


def convert_webm_to_wav(webm_path: Path, wav_path: Path) -> None:
    """Convert a webm file into a mono 16k wav file."""
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(webm_path),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(wav_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg was not found and is required for webm conversion.") from exc

    if result.returncode != 0:
        message = result.stderr.strip() or "ffmpeg conversion failed."
        raise RuntimeError(message)


def transcribe_audio(audio_path: Path, language: str | None = None) -> dict:
    options: dict[str, object] = {"fp16": False}
    normalized_language = normalize_language(language)
    if normalized_language:
        options["language"] = normalized_language

    result = model.transcribe(str(audio_path), **options)
    return {
        "text": result.get("text", "").strip(),
        "language": result.get("language", normalized_language),
        "segments": [
            {
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"].strip(),
            }
            for segment in result.get("segments", [])
        ],
    }


def validate_remote_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def transcribe_uploaded_path(input_path: Path, language: str | None) -> dict:
    if input_path.suffix.lower() == ".webm":
        wav_path = input_path.with_suffix(".wav")
        convert_webm_to_wav(input_path, wav_path)
        return transcribe_audio(wav_path, language)
    return transcribe_audio(input_path, language)


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "healthy",
            "service": "stt",
            "model": MODEL_SIZE,
            "language": DEFAULT_LANGUAGE,
            "host": STT_HOST,
            "port": STT_PORT,
        }
    )


@app.route("/api/stt", methods=["POST"])
def speech_to_text():
    if "file" not in request.files:
        return jsonify({"error": "An audio file is required."}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        return jsonify({"error": "Filename cannot be empty."}), 400

    language = normalize_language(request.form.get("language"))
    suffix = Path(uploaded_file.filename.lower()).suffix or ".bin"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / f"input{suffix}"
        uploaded_file.save(input_path)

        try:
            result = transcribe_uploaded_path(input_path, language)
        except Exception as exc:
            return jsonify({"error": f"Transcription failed: {exc}"}), 500

    return jsonify(
        {
            "success": True,
            "text": result["text"],
            "language": result["language"],
            "segments": result["segments"],
        }
    )


@app.route("/api/stt/url", methods=["POST"])
def speech_to_text_url():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    language = normalize_language(data.get("language"))

    if not url:
        return jsonify({"error": "A remote audio URL is required."}), 400
    if not validate_remote_url(url):
        return jsonify({"error": "Only http/https URLs are supported."}), 400

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except Exception as exc:
        return jsonify({"error": f"Download failed: {exc}"}), 400

    suffix = Path(urlparse(url).path).suffix or ".mp3"
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / f"input{suffix}"
        input_path.write_bytes(response.content)

        try:
            result = transcribe_uploaded_path(input_path, language)
        except Exception as exc:
            return jsonify({"error": f"Transcription failed: {exc}"}), 500

    return jsonify(
        {
            "success": True,
            "text": result["text"],
            "language": result["language"],
            "segments": result["segments"],
        }
    )


if __name__ == "__main__":
    print(f"STT server running at http://127.0.0.1:{STT_PORT}")
    print(f"Listening on {STT_HOST}:{STT_PORT}")
    print(f"Model: {MODEL_SIZE}")
    print(f"Default language: {DEFAULT_LANGUAGE}")
    app.run(host=STT_HOST, port=STT_PORT, debug=DEBUG)
