# TTS-STT 语音工具台

一个基于 Flask + React 的语音合成与识别工具，支持文本转语音、对话合成和语音转文本功能。

## 功能特性

- **文本转语音 (TTS)** - 使用 Microsoft Edge TTS，支持多种语音和语速调节
- **对话合成** - 输入对话文本，自动识别男女角色并生成长语音
- **语音转文本 (STT)** - 使用 OpenAI Whisper 进行语音识别
- **Web 界面** - 现代化的 React 前端，支持局域网访问

## 项目结构

```
├── web/                    # TTS 服务 (端口 5000)
│   ├── server.py           # Flask 后端
│   ├── requirements.txt    # Python 依赖
│   └── static/
│       └── index.html      # React 前端
├── stt/                    # STT 服务 (端口 5001)
│   ├── server.py           # Flask + Whisper 后端
│   └── requirements.txt    # Python 依赖
├── sessions/               # 生成的音频文件存储目录
├── start.bat               # Windows 启动脚本
├── tts.py                  # 命令行 TTS 工具
└── test_stt.py             # STT API 测试脚本
```

## 快速开始

### 环境要求

- Python 3.10+
- ffmpeg (用于音频处理)

### 安装依赖

```bash
# TTS 服务
cd web
pip install -r requirements.txt

# STT 服务
cd ../stt
pip install -r requirements.txt
```

### 启动服务

**Windows:**
```bash
# 双击运行
start.bat
```

**手动启动:**
```bash
# 终端 1 - TTS 服务
cd web
python server.py

# 终端 2 - STT 服务
cd stt
python server.py
```

### 访问地址

- **前端界面**: http://127.0.0.1:5000
- **TTS API**: http://127.0.0.1:5000/api
- **STT API**: http://127.0.0.1:5001/api

如需局域网访问，修改 `web/static/index.html` 中的 `API_BASE` 和 `STT_BASE` 地址。

## API 接口

### TTS 文本合成

```bash
POST /api/synthesize
Content-Type: application/json

{
  "text": "Q1\tHello world\t你好世界\nQ2\tHow are you?\t你好吗？",
  "topic": "my_topic",
  "voice": "jenny",
  "rate": "+0%"
}
```

### TTS 对话合成

```bash
POST /api/dialogue
Content-Type: application/json

{
  "text": "Mark: Hello.\nElena: Hi there.",
  "topic": "dialogue_topic",
  "maleVoice": "guy",
  "femaleVoice": "jenny",
  "rate": "+0%"
}
```

### STT 语音识别

```bash
POST /api/stt
Content-Type: multipart/form-data

file: <audio file>
language: en
```

### 更多接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/voices` | 获取可用语音列表 |
| GET | `/api/sessions` | 获取历史会话列表 |
| GET | `/api/download/{topic}` | 下载会话 ZIP |
| GET | `/api/download/{topic}/{file}` | 下载单个文件 |
| DELETE | `/api/sessions/{topic}` | 删除会话 |
| GET | `/health` | STT 健康检查 |

## 支持的语音

### 英文语音

| 名称 | 性别 | 说明 |
|------|------|------|
| jenny | 女 | 自然流畅 |
| guy | 男 | 自然流畅 |
| aria | 女 | 自然 |
| davis | 男 | 自然 |
| brian | 男 | 自然 |
| emma | 女 | 自然 |

### 中文语音

| 名称 | 性别 | 说明 |
|------|------|------|
| xiaoxiao | 女 | 自然流畅 |
| yunxi | 男 | 自然流畅 |
| yunjian | 男 | 新闻播报风格 |

## 输入格式

### TTS 支持的格式

**Q&A 格式:**
```
Q1	Hello world	你好世界
Q2	How are you?	你好吗？
```

**纯英文段落:**
```
This is the first paragraph.

This is the second paragraph.
```

**单段文本:**
```
Just paste your English text here.
```

### 对话合成格式

**带说话人定义:**
```
Mark(男), Elena(女)
Mark: Hello, how are you?
Elena: I'm fine, thanks!
```

**自动识别:**
```
Mark: Hello, how are you?
Elena: I'm fine, thanks!
```

## 技术栈

- **后端**: Flask, Flask-CORS
- **TTS**: edge-tts (Microsoft Edge TTS)
- **STT**: OpenAI Whisper
- **前端**: React 18 (CDN)
- **音频处理**: ffmpeg

## 许可证

MIT License