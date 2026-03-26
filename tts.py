#!/usr/bin/env python3
"""Microsoft Edge TTS command-line tool."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

try:
    import edge_tts
except ImportError:
    print("请先安装 edge-tts: pip install edge-tts")
    sys.exit(1)


CHINESE_VOICES = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "yunxi": "zh-CN-YunxiNeural",
    "yunjian": "zh-CN-YunjianNeural",
    "xiaoyi": "zh-CN-XiaoyiNeural",
    "yunxia": "zh-CN-YunxiaNeural",
    "xiaochen": "zh-CN-XiaochenNeural",
    "xiaohan": "zh-CN-XiaohanNeural",
    "xiaomeng": "zh-CN-XiaomengNeural",
    "xiaomo": "zh-CN-XiaomoNeural",
    "xiaoqiu": "zh-CN-XiaoqiuNeural",
    "xiaorui": "zh-CN-XiaoruiNeural",
    "xiaoshuang": "zh-CN-XiaoshuangNeural",
    "xiaoxuan": "zh-CN-XiaoxuanNeural",
    "xiaoyan": "zh-CN-XiaoyanNeural",
    "xiaoyou": "zh-CN-XiaoyouNeural",
    "yunfeng": "zh-CN-YunfengNeural",
    "yunhao": "zh-CN-YunhaoNeural",
    "yunxiang": "zh-CN-YunxiangNeural",
    "yunye": "zh-CN-YunyeNeural",
}

ENGLISH_VOICES = {
    "jenny": "en-US-JennyNeural",
    "guy": "en-US-GuyNeural",
    "aria": "en-US-AriaNeural",
    "davis": "en-US-DavisNeural",
    "amber": "en-US-AmberNeural",
    "ana": "en-US-AnaNeural",
    "ash": "en-US-AshNeural",
    "brian": "en-US-BrianNeural",
    "emma": "en-US-EmmaNeural",
    "eric": "en-US-EricNeural",
}

DEFAULT_VOICE = ENGLISH_VOICES["jenny"]
QUESTION_PATTERN = re.compile(r"^(Q\d+)[\s\t\.:,]+(.+)$", re.IGNORECASE)


TRANSLATION_TABLE = str.maketrans(
    {
        "：": ":",
        "，": ",",
        "、": ",",
        "。": ".",
        "（": "(",
        "）": ")",
    }
)


def extract_spoken_text(rest: str) -> str:
    """Extract the English content from a mixed-language question line."""
    normalized = rest.translate(TRANSLATION_TABLE)
    if "\t" in normalized:
        return normalized.split("\t", 1)[0].strip()

    chinese_start = next(
        (index for index, char in enumerate(normalized) if "\u4e00" <= char <= "\u9fff"),
        -1,
    )
    if chinese_start > 0:
        english = normalized[:chinese_start].strip()
        return re.sub(r"[\s\t\.,;:!?]+$", "", english)
    return normalized.strip()


def parse_questions(text: str) -> list[tuple[str, str]]:
    """Parse Q1/Q2... style text into (id, content) items."""
    questions: list[tuple[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.translate(TRANSLATION_TABLE).strip()
        if not line:
            continue
        match = QUESTION_PATTERN.match(line)
        if not match:
            continue
        question_id = match.group(1).upper()
        english = extract_spoken_text(match.group(2))
        if english:
            questions.append((question_id, english))
    return questions


def resolve_voice(voice_name: str) -> str:
    """Resolve shorthand voice names into full Edge voice ids."""
    voice_key = voice_name.lower()
    if voice_key in ENGLISH_VOICES:
        return ENGLISH_VOICES[voice_key]
    if voice_key in CHINESE_VOICES:
        return CHINESE_VOICES[voice_key]
    return voice_name


async def synthesize(
    text: str,
    output_file: str,
    voice: str | None = None,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> None:
    """Synthesize a single audio file."""
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice or DEFAULT_VOICE,
        rate=rate,
        pitch=pitch,
    )
    await communicate.save(output_file)


async def process_questions(
    text: str,
    output_dir: str,
    voice: str,
    rate: str,
    pitch: str,
    prefix: str = "",
) -> int:
    """Batch-synthesize question items from text."""
    questions = parse_questions(text)
    if not questions:
        print("未找到有效的 Q&A 格式文本。")
        return 0

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"找到 {len(questions)} 个条目，开始合成。")
    for index, (question_id, content) in enumerate(questions, start=1):
        file_name = f"{prefix}{question_id}.mp3" if prefix else f"{question_id}.mp3"
        file_path = output_path / file_name
        print(f"[{index}/{len(questions)}] {question_id} -> {file_path.name}")
        await synthesize(content, str(file_path), voice=voice, rate=rate, pitch=pitch)

    print(f"完成，共生成 {len(questions)} 个音频文件。")
    return len(questions)


async def list_voices(language: str = "en") -> None:
    """List available Edge voices filtered by locale prefix."""
    print("正在获取语音列表...")
    voices = await edge_tts.list_voices()
    filtered = [voice for voice in voices if voice["Locale"].startswith(language)]
    if not filtered:
        print(f"没有找到语言前缀为 {language} 的语音。")
        return

    print("-" * 90)
    for voice in filtered:
        print(f"{voice['ShortName']:<30} {voice['FriendlyName']}")
    print("-" * 90)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量将 Q&A 文本转换为音频文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  py -3 tts.py -i questions.txt\n"
            "  py -3 tts.py -t \"Q1\\tHello world\\t你好世界\"\n"
            "  py -3 tts.py -i questions.txt -o output -v jenny\n"
            "  py -3 tts.py -i questions.txt --rate=-10%\n"
            "  py -3 tts.py --list-voices --lang zh\n"
        ),
    )
    parser.add_argument("-i", "--input", help="输入文件路径")
    parser.add_argument("-t", "--text", help="直接输入的 Q&A 文本")
    parser.add_argument("-o", "--output", default="output", help="输出目录")
    parser.add_argument("-v", "--voice", default=DEFAULT_VOICE, help="语音名称或完整语音 ID")
    parser.add_argument("--rate", default="+0%", help="语速，例如 +10% 或 -20%")
    parser.add_argument("--pitch", default="+0Hz", help="音调，例如 +20Hz 或 -20Hz")
    parser.add_argument("--list-voices", action="store_true", help="列出可用语音")
    parser.add_argument("--lang", default="en", help="列出语音时使用的语言前缀")
    parser.add_argument("--prefix", default="", help="输出文件名前缀")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.list_voices:
        asyncio.run(list_voices(args.lang))
        return

    text = None
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    elif args.text:
        text = args.text

    if not text:
        parser.print_help()
        print("\n错误: 请通过 -i 或 -t 提供输入文本。")
        sys.exit(1)

    voice = resolve_voice(args.voice)
    asyncio.run(
        process_questions(
            text=text,
            output_dir=args.output,
            voice=voice,
            rate=args.rate,
            pitch=args.pitch,
            prefix=args.prefix,
        )
    )


if __name__ == "__main__":
    main()
