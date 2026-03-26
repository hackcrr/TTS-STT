#!/usr/bin/env python3
"""Flask backend for speech-to-text using Whisper."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
import whisper
from flask import Flask, jsonify, request
from flask_cors import CORS


FFMPEG_DIR = os.environ.get(
    "FFMPEG_DIR",
    r"C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links",
)
if FFMPEG_DIR and Path(FFMPEG_DIR).exists():
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
DEFAULT_LANGUAGE = os.environ.get("WHISPER_LANG", "en")
DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"

app = Flask(__name__)
CORS(app)

print(f"Loading Whisper model: {MODEL_SIZE}")
model = whisper.load_model(MODEL_SIZE)
print("Whisper model loaded.")


def normalize_language(language: str | None) -> str | None:
    language = (language or DEFAULT_LANGUAGE or "").strip().lower()
    return language or None


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
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 ffmpeg，无法转换 webm 音频。") from exc

    if result.returncode != 0:
        message = result.stderr.strip() or "ffmpeg 转换失败。"
        raise RuntimeError(message)


def transcribe_audio(audio_path: Path, language: str | None = None) -> dict:
    options = {"fp16": False}
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


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "healthy",
            "service": "stt",
            "model": MODEL_SIZE,
            "language": DEFAULT_LANGUAGE,
        }
    )


@app.route("/api/stt", methods=["POST"])
def speech_to_text():
    if "file" not in request.files:
        return jsonify({"error": "请提供音频文件。"}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        return jsonify({"error": "文件名不能为空。"}), 400

    language = normalize_language(request.form.get("language"))
    suffix = Path(uploaded_file.filename.lower()).suffix or ".bin"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / f"input{suffix}"
        uploaded_file.save(input_path)

        if suffix == ".webm":
            wav_path = temp_path / "converted.wav"
            try:
                convert_webm_to_wav(input_path, wav_path)
            except RuntimeError as exc:
                return jsonify({"error": str(exc)}), 500
            audio_path = wav_path
        else:
            audio_path = input_path

        try:
            result = transcribe_audio(audio_path, language)
        except Exception as exc:
            return jsonify({"error": f"转录失败: {exc}"}), 500

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
        return jsonify({"error": "请提供音频 URL。"}), 400
    if not validate_remote_url(url):
        return jsonify({"error": "仅支持 http/https 音频 URL。"}), 400

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except Exception as exc:
        return jsonify({"error": f"下载失败: {exc}"}), 400

    suffix = Path(urlparse(url).path).suffix or ".mp3"
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / f"input{suffix}"
        input_path.write_bytes(response.content)

        if suffix == ".webm":
            wav_path = temp_path / "converted.wav"
            try:
                convert_webm_to_wav(input_path, wav_path)
            except RuntimeError as exc:
                return jsonify({"error": str(exc)}), 500
            audio_path = wav_path
        else:
            audio_path = input_path

        try:
            result = transcribe_audio(audio_path, language)
        except Exception as exc:
            return jsonify({"error": f"转录失败: {exc}"}), 500

    return jsonify(
        {
            "success": True,
            "text": result["text"],
            "language": result["language"],
            "segments": result["segments"],
        }
    )


if __name__ == "__main__":
    host = os.environ.get("STT_HOST", "0.0.0.0")
    port = int(os.environ.get("STT_PORT", "5001"))

    print(f"STT 服务启动: http://127.0.0.1:{port}")
    print(f"模型: {MODEL_SIZE}")
    print(f"默认语言: {DEFAULT_LANGUAGE}")
    app.run(host=host, port=port, debug=DEBUG)
