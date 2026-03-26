#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simple command-line tester for the STT API."""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

STT_BASE_URL = os.environ.get("STT_BASE_URL", "http://127.0.0.1:5001")
STT_API_URL = f"{STT_BASE_URL}/api/stt"


def test_health() -> bool:
    print("=" * 50)
    print("检查 STT 服务健康状态")
    print("=" * 50)
    try:
        response = requests.get(f"{STT_BASE_URL}/health", timeout=5)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        print(f"[ERROR] 连接失败: {exc}")
        return False

    print(f"[OK] 状态: {data.get('status')}")
    print(f"[OK] 模型: {data.get('model')}")
    print(f"[OK] 默认语言: {data.get('language')}")
    return True


def transcribe_file(file_path: str, language: str = "en") -> dict | None:
    path = Path(file_path)
    if not path.exists():
        print(f"[ERROR] 文件不存在: {path}")
        return None

    print("=" * 50)
    print(f"转录文件: {path.name}")
    print(f"语言: {language}")
    print("=" * 50)

    try:
        with path.open("rb") as file_handle:
            response = requests.post(
                STT_API_URL,
                files={"file": (path.name, file_handle)},
                data={"language": language},
                timeout=120,
            )
        result = response.json()
    except requests.exceptions.Timeout:
        print("[ERROR] 请求超时。")
        return None
    except Exception as exc:
        print(f"[ERROR] 请求失败: {exc}")
        return None

    if response.ok and result.get("success"):
        print("[OK] 转录成功")
        print("-" * 50)
        print(result.get("text", ""))
        print("-" * 50)
        for segment in result.get("segments", []):
            print(f"[{segment['start']:.1f}s - {segment['end']:.1f}s] {segment['text']}")
        return result

    print(f"[ERROR] 转录失败: {result.get('error', '未知错误')}")
    return None


def transcribe_url(url: str, language: str = "en") -> dict | None:
    print("=" * 50)
    print(f"转录 URL: {url}")
    print(f"语言: {language}")
    print("=" * 50)

    try:
        response = requests.post(
            f"{STT_API_URL}/url",
            json={"url": url, "language": language},
            timeout=180,
        )
        result = response.json()
    except Exception as exc:
        print(f"[ERROR] 请求失败: {exc}")
        return None

    if response.ok and result.get("success"):
        print("[OK] 转录成功")
        print(result.get("text", ""))
        return result

    print(f"[ERROR] 转录失败: {result.get('error', '未知错误')}")
    return None


def main() -> None:
    if len(sys.argv) < 2:
        print("用法:")
        print("  py -3 test_stt.py <音频文件> [语言]")
        print("  py -3 test_stt.py --url <音频URL> [语言]")
        print("  py -3 test_stt.py --health")
        return

    if sys.argv[1] == "--health":
        test_health()
        return

    if sys.argv[1] == "--url":
        if len(sys.argv) < 3:
            print("请提供音频 URL。")
            return
        language = sys.argv[3] if len(sys.argv) > 3 else "en"
        transcribe_url(sys.argv[2], language)
        return

    if not test_health():
        print("\n请先启动 STT 服务。")
        return

    language = sys.argv[2] if len(sys.argv) > 2 else "en"
    transcribe_file(sys.argv[1], language)


if __name__ == "__main__":
    main()
