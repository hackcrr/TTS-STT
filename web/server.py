#!/usr/bin/env python3
"""Flask backend for TTS APIs and the embedded web UI."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

try:
    import edge_tts
except ImportError:
    print("Please install edge-tts first: pip install edge-tts")
    raise SystemExit(1)


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from env_utils import env_int, load_env_files

load_env_files(ROOT_DIR)

OUTPUT_DIR = ROOT_DIR / "sessions"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TTS_HOST = os.environ.get("TTS_HOST", "0.0.0.0")
TTS_PORT = env_int("TTS_PORT", 5000)
STT_PORT = env_int("STT_PORT", 5001)
DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
TTS_PUBLIC_BASE_URL = os.environ.get("TTS_PUBLIC_BASE_URL", "").rstrip("/")
STT_PUBLIC_BASE_URL = os.environ.get("STT_PUBLIC_BASE_URL", "").rstrip("/")
STT_PUBLIC_HOST = os.environ.get("STT_PUBLIC_HOST", "").strip()
STT_PUBLIC_SCHEME = os.environ.get("STT_PUBLIC_SCHEME", "").strip()

ENGLISH_VOICES = {
    "jenny": "en-US-JennyNeural",
    "guy": "en-US-GuyNeural",
    "aria": "en-US-AriaNeural",
    "davis": "en-US-DavisNeural",
    "amber": "en-US-AmberNeural",
    "brian": "en-US-BrianNeural",
    "emma": "en-US-EmmaNeural",
}

MALE_VOICES = {
    "guy": "en-US-GuyNeural",
    "davis": "en-US-DavisNeural",
    "brian": "en-US-BrianNeural",
}

FEMALE_VOICES = {
    "jenny": "en-US-JennyNeural",
    "aria": "en-US-AriaNeural",
    "emma": "en-US-EmmaNeural",
}

MALE_NAMES = {
    "mark",
    "john",
    "david",
    "michael",
    "james",
    "robert",
    "william",
    "tom",
    "guy",
}

FEMALE_NAMES = {
    "elena",
    "jenny",
    "emma",
    "aria",
    "sarah",
    "lisa",
    "mary",
    "anna",
    "kate",
}

QUESTION_PATTERN = re.compile(r"^(Q\d+)[\s\t\.:,]+(.+)$", re.IGNORECASE)
PUNCT_TRANSLATION = str.maketrans(
    {
        "\uFF1A": ":",
        "\uFF0C": ",",
        "\u3002": ".",
        "\uFF08": "(",
        "\uFF09": ")",
        "\u3001": ",",
        "\uFF1F": "?",
        "\uFF1B": ";",
        "\uFF01": "!",
    }
)

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)


def parse_questions(text: str) -> list[tuple[str, str]]:
    """Parse supported input formats into synthesize tasks."""
    questions: list[tuple[str, str]] = []
    normalized_text = normalize_text(text)
    lines = normalized_text.strip().splitlines()
    has_q_format = any(QUESTION_PATTERN.match(line.strip()) for line in lines if line.strip())

    if has_q_format:
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            match = QUESTION_PATTERN.match(line)
            if not match:
                continue

            question_id = match.group(1).upper()
            rest = match.group(2)

            if "\t" in rest:
                spoken_text = rest.split("\t", 1)[0].strip()
            else:
                chinese_start = next(
                    (index for index, char in enumerate(rest) if "\u4e00" <= char <= "\u9fff"),
                    -1,
                )
                spoken_text = rest[:chinese_start].strip() if chinese_start > 0 else rest.strip()
                spoken_text = re.sub(r"[\s\t\.,;:!?]+$", "", spoken_text)

            if spoken_text:
                questions.append((question_id, spoken_text))
        return questions

    non_empty_lines = [line.strip() for line in lines if line.strip()]
    if not non_empty_lines:
        return []

    english_chars = sum(1 for char in normalized_text if char.isascii() and char.isalpha())
    total_alpha = sum(1 for char in normalized_text if char.isalpha())
    is_english_dominant = total_alpha == 0 or english_chars / total_alpha > 0.7

    if is_english_dominant:
        paragraph_index = 1
        for line in non_empty_lines:
            if len(line) > 10:
                questions.append((f"P{paragraph_index}", line))
                paragraph_index += 1

        if len(questions) == 1:
            return [("Full", questions[0][1])]
        return questions

    return [("Full", " ".join(non_empty_lines))]


def parse_dialogue(
    text: str,
    male_speaker: str | None = None,
    female_speaker: str | None = None,
) -> tuple[list[dict[str, str]], str | None, str | None]:
    """Parse dialogue rows like `Mark: Hello` into segments."""
    lines = normalize_text(text).strip().splitlines()
    dialogues: list[dict[str, str]] = []

    first_line = lines[0].strip() if lines else ""
    speaker_def_match = re.match(
        r"^([A-Za-z]+)\s*\(?(male)?\)?\s*,\s*([A-Za-z]+)\s*\(?(female)?\)?$",
        first_line,
        re.IGNORECASE,
    )

    if speaker_def_match:
        male_speaker = male_speaker or speaker_def_match.group(1)
        female_speaker = female_speaker or speaker_def_match.group(3)
        lines = lines[1:]

    for index, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        match = re.match(r"^([A-Za-z]+)\s*:\s*(.+)$", line)
        if not match:
            continue

        speaker = match.group(1)
        content = match.group(2).strip()
        speaker_key = speaker.lower()

        if male_speaker and speaker_key == male_speaker.lower():
            gender = "male"
        elif female_speaker and speaker_key == female_speaker.lower():
            gender = "female"
        elif speaker_key in MALE_NAMES:
            gender = "male"
        elif speaker_key in FEMALE_NAMES:
            gender = "female"
        else:
            gender = "male" if len(dialogues) % 2 == 0 else "female"

        dialogues.append(
            {
                "id": f"D{index}",
                "speaker": speaker,
                "gender": gender,
                "text": content,
            }
        )

    return dialogues, male_speaker, female_speaker


def normalize_text(text: str) -> str:
    return text.translate(PUNCT_TRANSLATION).replace("\u7537", "male").replace("\u5973", "female")


def sanitize_topic(topic: str, prefix: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", topic.strip())
    if cleaned:
        return cleaned
    return datetime.now().strftime(f"{prefix}_%Y%m%d_%H%M%S")


async def synthesize_text(text: str, output_file: str, voice: str, rate: str, pitch: str) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_file)


async def process_session(
    text: str,
    topic: str,
    voice: str,
    rate: str,
    pitch: str,
) -> tuple[list[dict[str, str]], str | None]:
    questions = parse_questions(text)
    if not questions:
        return [], "No valid text was found to synthesize."

    session_dir = OUTPUT_DIR / topic
    session_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, str]] = []
    for question_id, content in questions:
        filename = f"{question_id}.mp3"
        filepath = session_dir / filename
        await synthesize_text(content, str(filepath), voice, rate, pitch)
        results.append({"id": question_id, "text": content, "file": filename})

    return results, None


async def process_dialogue(
    text: str,
    topic: str,
    male_voice: str,
    female_voice: str,
    rate: str,
    pitch: str,
) -> tuple[dict[str, object] | None, str | None, str | None, str | None]:
    dialogues, male_speaker, female_speaker = parse_dialogue(text)
    if not dialogues:
        return None, "No valid dialogue rows were found.", None, None

    session_dir = OUTPUT_DIR / topic
    session_dir.mkdir(parents=True, exist_ok=True)

    segment_files: list[Path] = []
    for dialogue in dialogues:
        if dialogue["gender"] == "male":
            voice = MALE_VOICES.get(male_voice, MALE_VOICES["guy"])
        else:
            voice = FEMALE_VOICES.get(female_voice, FEMALE_VOICES["jenny"])

        segment_path = session_dir / f"_temp_{dialogue['id']}.mp3"
        await synthesize_text(dialogue["text"], str(segment_path), voice, rate, pitch)
        segment_files.append(segment_path)

    output_path = session_dir / "dialogue.mp3"
    with output_path.open("wb") as outfile:
        for segment_file in segment_files:
            outfile.write(segment_file.read_bytes())

    for segment_file in segment_files:
        segment_file.unlink(missing_ok=True)

    result = {
        "id": "dialogue",
        "file": "dialogue.mp3",
        "text": f"{len(dialogues)} dialogue segments",
        "segments": dialogues,
        "speakers": {"male": male_speaker, "female": female_speaker},
    }
    return result, None, male_speaker, female_speaker


def current_request_hostname() -> str:
    host = request.host.split(":", 1)[0].strip()
    return host or "127.0.0.1"


def build_stt_base_url() -> str:
    if STT_PUBLIC_BASE_URL:
        return STT_PUBLIC_BASE_URL

    scheme = STT_PUBLIC_SCHEME or request.scheme or "http"
    host = STT_PUBLIC_HOST or current_request_hostname()
    return f"{scheme}://{host}:{STT_PORT}"


@app.route("/")
def index():
    return send_from_directory(Path(__file__).resolve().parent / "static", "index.html")


@app.route("/app-config.js")
def app_config():
    api_base = f"{TTS_PUBLIC_BASE_URL}/api" if TTS_PUBLIC_BASE_URL else "/api"
    stt_base = f"{build_stt_base_url()}/api"
    payload = {
        "apiBase": api_base,
        "sttBase": stt_base,
        "ttsPort": TTS_PORT,
        "sttPort": STT_PORT,
    }
    body = f"window.APP_CONFIG = {json.dumps(payload, ensure_ascii=False)};"
    return app.response_class(body, mimetype="application/javascript")


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "healthy",
            "service": "tts",
            "host": TTS_HOST,
            "port": TTS_PORT,
            "sessions_dir": str(OUTPUT_DIR),
        }
    )


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(
        {
            "apiBase": f"{TTS_PUBLIC_BASE_URL}/api" if TTS_PUBLIC_BASE_URL else "/api",
            "sttBase": f"{build_stt_base_url()}/api",
            "ttsPort": TTS_PORT,
            "sttPort": STT_PORT,
        }
    )


@app.route("/api/voices", methods=["GET"])
def get_voices():
    return jsonify(
        {
            "voices": [
                {"id": key, "name": value.replace("Neural", "").replace("-", " ")}
                for key, value in ENGLISH_VOICES.items()
            ],
            "maleVoices": list(MALE_VOICES.keys()),
            "femaleVoices": list(FEMALE_VOICES.keys()),
        }
    )


@app.route("/api/synthesize", methods=["POST"])
def synthesize():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    topic = sanitize_topic(data.get("topic") or "", "session")
    voice_key = (data.get("voice") or "jenny").strip().lower()
    rate = data.get("rate") or "+0%"
    pitch = data.get("pitch") or "+0Hz"

    if not text:
        return jsonify({"error": "Text is required."}), 400

    voice = ENGLISH_VOICES.get(voice_key, ENGLISH_VOICES["jenny"])
    results, error = asyncio.run(process_session(text, topic, voice, rate, pitch))
    if error:
        return jsonify({"error": error}), 400

    return jsonify(
        {
            "success": True,
            "topic": topic,
            "results": results,
            "download_url": f"/api/download/{topic}",
        }
    )


@app.route("/api/dialogue", methods=["POST"])
def synthesize_dialogue():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    topic = sanitize_topic(data.get("topic") or "", "dialogue")
    male_voice = (data.get("maleVoice") or "guy").strip().lower()
    female_voice = (data.get("femaleVoice") or "jenny").strip().lower()
    rate = data.get("rate") or "+0%"
    pitch = data.get("pitch") or "+0Hz"

    if not text:
        return jsonify({"error": "Text is required."}), 400

    result, error, male_speaker, female_speaker = asyncio.run(
        process_dialogue(text, topic, male_voice, female_voice, rate, pitch)
    )
    if error:
        return jsonify({"error": error}), 400

    return jsonify(
        {
            "success": True,
            "topic": topic,
            "maleSpeaker": male_speaker,
            "femaleSpeaker": female_speaker,
            "result": result,
            "download_url": f"/api/download/{topic}/dialogue.mp3",
        }
    )


@app.route("/api/download/<topic>")
def download_session(topic: str):
    session_dir = OUTPUT_DIR / topic
    if not session_dir.exists():
        return jsonify({"error": "Session not found."}), 404

    zip_path = OUTPUT_DIR / f"{topic}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in session_dir.glob("*.mp3"):
            zipf.write(file, file.name)

    return send_file(zip_path, as_attachment=True, download_name=f"{topic}.zip")


@app.route("/api/download/<topic>/<filename>")
def download_file(topic: str, filename: str):
    filepath = OUTPUT_DIR / topic / filename
    if not filepath.exists():
        return jsonify({"error": "File not found."}), 404
    return send_file(filepath, as_attachment=True)


@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    sessions: list[dict[str, object]] = []
    for session_dir in OUTPUT_DIR.iterdir():
        if not session_dir.is_dir():
            continue

        files = sorted(file.name for file in session_dir.glob("*.mp3"))
        sessions.append(
            {
                "topic": session_dir.name,
                "file_count": len(files),
                "files": files,
            }
        )

    return jsonify({"sessions": sorted(sessions, key=lambda item: item["topic"], reverse=True)})


@app.route("/api/sessions/<topic>", methods=["DELETE"])
def delete_session(topic: str):
    session_dir = OUTPUT_DIR / topic
    if not session_dir.exists():
        return jsonify({"error": "Session not found."}), 404

    shutil.rmtree(session_dir)

    zip_path = OUTPUT_DIR / f"{topic}.zip"
    if zip_path.exists():
        zip_path.unlink()

    return jsonify({"success": True})


@app.route("/static/<path:filename>")
def serve_static(filename: str):
    return send_from_directory(Path(__file__).resolve().parent / "static", filename)


if __name__ == "__main__":
    print(f"TTS server running at http://127.0.0.1:{TTS_PORT}")
    print(f"Listening on {TTS_HOST}:{TTS_PORT}")
    print(f"Sessions directory: {OUTPUT_DIR}")
    app.run(host=TTS_HOST, port=TTS_PORT, debug=DEBUG)
