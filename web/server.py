#!/usr/bin/env python3
"""
TTS Web Server - Flask 后端
提供语音合成 API 和文件下载功能
"""

import os
import re
import shutil
import zipfile
import asyncio
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

try:
    import edge_tts
except ImportError:
    print("请先安装 edge-tts: pip install edge-tts")
    exit(1)

app = Flask(__name__)
CORS(app)

# 配置
BASE_DIR = Path(__file__).parent.parent.absolute()
OUTPUT_DIR = BASE_DIR / "sessions"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 英文语音选项
ENGLISH_VOICES = {
    "jenny": "en-US-JennyNeural",
    "guy": "en-US-GuyNeural",
    "aria": "en-US-AriaNeural",
    "davis": "en-US-DavisNeural",
    "amber": "en-US-AmberNeural",
    "brian": "en-US-BrianNeural",
    "emma": "en-US-EmmaNeural",
}

# 男性语音
MALE_VOICES = {
    "guy": "en-US-GuyNeural",
    "davis": "en-US-DavisNeural",
    "brian": "en-US-BrianNeural",
}

# 女性语音
FEMALE_VOICES = {
    "jenny": "en-US-JennyNeural",
    "aria": "en-US-AriaNeural",
    "emma": "en-US-EmmaNeural",
}


def parse_questions(text: str):
    """
    解析文本，提取需要合成语音的内容

    支持三种格式：
    1. Q&A 格式: Q1\tEnglish text\t中文翻译
    2. 段落格式: 每行一段纯文本（自动检测）
    3. 整体格式: 纯文本直接整体合成
    """
    questions = []
    lines = text.strip().split('\n')

    # 检查是否有 Q1、Q2 格式
    has_q_format = any(re.match(r'^Q\d+[\s\t\.：:]', line.strip()) for line in lines if line.strip())

    if has_q_format:
        # 处理 Q&A 格式
        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = re.match(r'^(Q\d+)[\s\t\.：:]+(.+)$', line)
            if match:
                q_id = match.group(1)
                rest = match.group(2)

                # 如果有制表符，取第二列（英文）
                if '\t' in rest:
                    parts = rest.split('\t')
                    english = parts[0].strip()
                else:
                    # 找到第一个中文字符的位置
                    chinese_start = -1
                    for i, char in enumerate(rest):
                        if '\u4e00' <= char <= '\u9fff':
                            chinese_start = i
                            break

                    if chinese_start > 0:
                        english = rest[:chinese_start].strip()
                        english = re.sub(r'[\s\t\.，。]+$', '', english)
                    else:
                        english = rest.strip()

                if english:
                    questions.append((q_id, english))
    else:
        # 检测是否是纯英文文本（或主要是英文）
        non_empty_lines = [line.strip() for line in lines if line.strip()]

        if not non_empty_lines:
            return []

        # 检测文本是否主要是英文
        english_chars = sum(1 for c in text if c.isascii() and c.isalpha())
        total_alpha = sum(1 for c in text if c.isalpha())
        is_english_dominant = total_alpha == 0 or english_chars / total_alpha > 0.7

        if is_english_dominant:
            # 纯英文文本：按段落分割，每个非空段落生成一个音频
            para_idx = 1
            for line in non_empty_lines:
                if len(line) > 10:  # 忽略太短的行
                    questions.append((f"P{para_idx}", line))
                    para_idx += 1

            # 如果只有一段，使用 "Full" 作为 ID
            if len(questions) == 1:
                questions = [("Full", questions[0][1])]
        else:
            # 中文文本或混合文本：整体合成
            clean_text = ' '.join(non_empty_lines)
            questions.append(("Full", clean_text))

    return questions


def parse_dialogue(text: str, male_speaker: str = None, female_speaker: str = None):
    """
    解析对话格式文本

    格式示例：
    Mark: Hello, how are you?
    Elena: I'm fine, thanks.

    或者：
    Mark(男), Elena(女)
    Mark: Hello...
    Elena: Hi...
    """
    lines = text.strip().split('\n')
    dialogues = []

    # 默认说话人性别映射
    speaker_gender = {}

    # 检测第一行是否是说话人定义
    first_line = lines[0].strip() if lines else ""
    speaker_def_match = re.match(r'^([A-Za-z]+)\s*[\(（]男[\)）]\s*[,，]\s*([A-Za-z]+)\s*[\(（]女[\)）]', first_line)

    if speaker_def_match:
        male_speaker = male_speaker or speaker_def_match.group(1)
        female_speaker = female_speaker or speaker_def_match.group(2)
        lines = lines[1:]  # 跳过第一行

    # 解析对话行
    for idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # 匹配 "Name: text" 格式
        match = re.match(r'^([A-Za-z]+)\s*[:：]\s*(.+)$', line)
        if match:
            speaker = match.group(1)
            text_content = match.group(2).strip()

            # 推断性别
            if male_speaker and speaker.lower() == male_speaker.lower():
                gender = "male"
            elif female_speaker and speaker.lower() == female_speaker.lower():
                gender = "female"
            else:
                # 根据常见名字猜测
                male_names = ['mark', 'john', 'david', 'michael', 'james', 'robert', 'william', 'tom', 'guy']
                female_names = ['elena', 'jenny', 'emma', 'aria', 'sarah', 'lisa', 'mary', 'anna', 'kate']
                if speaker.lower() in male_names:
                    gender = "male"
                elif speaker.lower() in female_names:
                    gender = "female"
                else:
                    # 默认交替
                    gender = "male" if len(dialogues) % 2 == 0 else "female"

            dialogues.append({
                "id": f"D{idx + 1}",
                "speaker": speaker,
                "gender": gender,
                "text": text_content
            })

    return dialogues, male_speaker, female_speaker


async def synthesize_text(text: str, output_file: str, voice: str, rate: str, pitch: str):
    """合成单个文本"""
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_file)


async def process_session(text: str, topic: str, voice: str, rate: str, pitch: str):
    """处理一个会话的所有问题"""
    questions = parse_questions(text)

    if not questions:
        return [], "未找到有效的问答格式文本"

    # 创建会话目录
    session_dir = OUTPUT_DIR / topic
    session_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for q_id, english in questions:
        filepath = session_dir / f"{q_id}.mp3"
        await synthesize_text(english, str(filepath), voice, rate, pitch)
        results.append({
            "id": q_id,
            "text": english,
            "file": f"{q_id}.mp3"
        })

    return results, None


async def process_dialogue(text: str, topic: str, male_voice: str, female_voice: str, rate: str, pitch: str):
    """处理对话合成"""
    dialogues, male_speaker, female_speaker = parse_dialogue(text)

    if not dialogues:
        return None, "未找到有效的对话格式文本", None, None

    # 创建会话目录
    session_dir = OUTPUT_DIR / topic
    session_dir.mkdir(parents=True, exist_ok=True)

    # 生成每个对话片段
    segment_files = []
    for dialogue in dialogues:
        # 根据性别选择语音
        if dialogue["gender"] == "male":
            voice = MALE_VOICES.get(male_voice, MALE_VOICES["guy"])
        else:
            voice = FEMALE_VOICES.get(female_voice, FEMALE_VOICES["jenny"])

        # 生成临时片段文件
        segment_path = session_dir / f"_temp_{dialogue['id']}.mp3"
        await synthesize_text(dialogue["text"], str(segment_path), voice, rate, pitch)
        segment_files.append(segment_path)

    # 合并所有片段为一个长语音（MP3可以直接拼接）
    output_path = session_dir / "dialogue.mp3"
    with open(output_path, 'wb') as outfile:
        for seg_file in segment_files:
            with open(seg_file, 'rb') as infile:
                outfile.write(infile.read())

    # 清理临时文件
    for seg_file in segment_files:
        seg_file.unlink(missing_ok=True)

    # 返回结果
    result = {
        "id": "dialogue",
        "file": "dialogue.mp3",
        "text": f"共 {len(dialogues)} 段对话",
        "segments": dialogues,
        "speakers": {
            "male": male_speaker,
            "female": female_speaker
        }
    }

    return result, None, male_speaker, female_speaker


@app.route('/')
def index():
    """返回前端页面"""
    return send_from_directory(BASE_DIR / 'web' / 'static', 'index.html')


@app.route('/api/voices', methods=['GET'])
def get_voices():
    """获取可用语音列表"""
    return jsonify({
        "voices": [
            {"id": k, "name": v.replace("Neural", "").replace("-", " ")}
            for k, v in ENGLISH_VOICES.items()
        ],
        "maleVoices": list(MALE_VOICES.keys()),
        "femaleVoices": list(FEMALE_VOICES.keys())
    })


@app.route('/api/synthesize', methods=['POST'])
def synthesize():
    """合成语音 API"""
    data = request.json
    text = data.get('text', '')
    topic = data.get('topic', '').strip()
    voice_key = data.get('voice', 'jenny')
    rate = data.get('rate', '+0%')
    pitch = data.get('pitch', '+0Hz')

    if not text:
        return jsonify({"error": "请提供文本"}), 400

    if not topic:
        topic = datetime.now().strftime("session_%Y%m%d_%H%M%S")

    # 清理主题名称，移除非法字符
    topic = re.sub(r'[<>:"/\\|?*]', '_', topic)

    voice = ENGLISH_VOICES.get(voice_key, ENGLISH_VOICES['jenny'])

    # 异步执行合成
    results, error = asyncio.run(process_session(text, topic, voice, rate, pitch))

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "success": True,
        "topic": topic,
        "results": results,
        "download_url": f"/api/download/{topic}"
    })


@app.route('/api/dialogue', methods=['POST'])
def synthesize_dialogue():
    """对话语音合成 API"""
    data = request.json
    text = data.get('text', '')
    topic = data.get('topic', '').strip()
    male_voice = data.get('maleVoice', 'guy')
    female_voice = data.get('femaleVoice', 'jenny')
    rate = data.get('rate', '+0%')
    pitch = data.get('pitch', '+0Hz')

    if not text:
        return jsonify({"error": "请提供文本"}), 400

    if not topic:
        topic = datetime.now().strftime("dialogue_%Y%m%d_%H%M%S")

    # 清理主题名称，移除非法字符
    topic = re.sub(r'[<>:"/\\|?*]', '_', topic)

    # 异步执行合成
    result, error, male_speaker, female_speaker = asyncio.run(
        process_dialogue(text, topic, male_voice, female_voice, rate, pitch)
    )

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "success": True,
        "topic": topic,
        "maleSpeaker": male_speaker,
        "femaleSpeaker": female_speaker,
        "result": result,
        "download_url": f"/api/download/{topic}/dialogue.mp3"
    })


@app.route('/api/download/<topic>')
def download_session(topic):
    """下载整个会话的压缩包"""
    session_dir = OUTPUT_DIR / topic

    if not session_dir.exists():
        return jsonify({"error": "会话不存在"}), 404

    # 创建压缩包
    zip_path = OUTPUT_DIR / f"{topic}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in session_dir.glob('*.mp3'):
            zipf.write(file, file.name)

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f"{topic}.zip"
    )


@app.route('/api/download/<topic>/<filename>')
def download_file(topic, filename):
    """下载单个文件"""
    session_dir = OUTPUT_DIR / topic
    filepath = session_dir / filename

    if not filepath.exists():
        return jsonify({"error": "文件不存在"}), 404

    return send_file(filepath, as_attachment=True)


@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    """列出所有会话"""
    sessions = []
    for session_dir in OUTPUT_DIR.iterdir():
        if session_dir.is_dir():
            files = list(session_dir.glob('*.mp3'))
            sessions.append({
                "topic": session_dir.name,
                "file_count": len(files),
                "files": [f.name for f in sorted(files)]
            })
    return jsonify({"sessions": sorted(sessions, key=lambda x: x['topic'], reverse=True)})


@app.route('/api/sessions/<topic>', methods=['DELETE'])
def delete_session(topic):
    """删除会话"""
    session_dir = OUTPUT_DIR / topic

    if not session_dir.exists():
        return jsonify({"error": "会话不存在"}), 404

    shutil.rmtree(session_dir)

    # 同时删除压缩包
    zip_path = OUTPUT_DIR / f"{topic}.zip"
    if zip_path.exists():
        zip_path.unlink()

    return jsonify({"success": True})


# 静态文件服务
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(BASE_DIR / 'web' / 'static', filename)


if __name__ == '__main__':
    print(f"服务器启动在 http://127.0.0.1:5000")
    print(f"输出目录: {OUTPUT_DIR}")
    app.run(host='0.0.0.0', port=5000, debug=True)