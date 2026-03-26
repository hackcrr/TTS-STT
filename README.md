# TTS-STT Voice Toolkit

一个基于 Flask + React 的语音工具项目，提供：

- 文本转语音（TTS）
- 对话语音合成
- 语音转文本（STT / Whisper）
- MCP 封装，方便接入 Claude Code、Claude Desktop 或其他 MCP Client

## 功能概览

### 1. 文本转语音

- 使用 `edge-tts`
- 支持多种英文音色
- 支持语速、音高调整
- 支持 Q&A 文本、段落文本、整段文本

### 2. 对话合成

- 输入 `Speaker: text` 格式的对话
- 自动识别男女角色，或按顺序交替分配
- 输出一段完整对话音频

### 3. 语音转文本

- 使用 OpenAI Whisper
- 支持上传本地音频文件
- 支持传入远程音频 URL

### 4. Web UI

- 前端是单文件 React 页面
- UI 不再写死某台机器的 IP
- TTS / STT 地址支持运行时自动推导和环境变量覆盖

### 5. MCP 封装

- 提供 `stdio` MCP 服务
- 可把现有 HTTP 接口封装成 MCP 工具
- 可供本机或局域网内其他机器的 MCP Client 使用

## 项目结构

```text
.
├─ web/
│  ├─ server.py
│  ├─ requirements.txt
│  └─ static/
│     └─ index.html
├─ stt/
│  ├─ server.py
│  └─ requirements.txt
├─ sessions/
├─ env_utils.py
├─ mcp_server.py
├─ start.bat
├─ requirements.txt
├─ .env.example
```

## 技术栈

- Backend: Flask, Flask-CORS
- TTS: edge-tts
- STT: openai-whisper
- Frontend: React 18 (CDN)
- MCP: stdio MCP wrapper

## 环境要求

- Windows 10 / 11
- Python 3.10+
- ffmpeg

## 安装依赖

### TTS 服务

```bat
cd web
python -m pip install -r requirements.txt
```

### STT 服务

```bat
cd stt
python -m pip install -r requirements.txt
```

### MCP 包装层

```bat
cd D:\语音合成
python -m pip install -r requirements.txt
```

## 环境变量

先复制一份配置文件：

```bat
copy .env.example .env
```

常用配置项：

```env
FLASK_DEBUG=1

TTS_HOST=0.0.0.0
TTS_PORT=5000

STT_HOST=0.0.0.0
STT_PORT=5001

WHISPER_MODEL=small
WHISPER_LANG=en

MCP_TTS_BASE_URL=http://127.0.0.1:5000
MCP_STT_BASE_URL=http://127.0.0.1:5001
```

可选公网 / 局域网覆盖项：

```env
TTS_PUBLIC_BASE_URL=
STT_PUBLIC_BASE_URL=
STT_PUBLIC_HOST=
STT_PUBLIC_SCHEME=http
```

## 自动 IP 说明

前端现在不再把 API 写死为固定 IP。

默认行为：

- TTS API 使用相对路径 `/api`
- STT API 使用“当前浏览器访问的主机名 + `STT_PORT`”

例如你在另一台机器上通过：

```text
http://192.168.1.25:5000
```

打开页面，那么前端默认会请求：

- `http://192.168.1.25:5000/api`
- `http://192.168.1.25:5001/api`

如果你需要固定对外地址，再配置：

- `TTS_PUBLIC_BASE_URL`
- `STT_PUBLIC_BASE_URL`

## 启动方式

### 一键启动

```bat
start.bat
```

### 手动启动

TTS:

```bat
cd web
python server.py
```

STT:

```bat
cd stt
python server.py
```

### 健康检查

- TTS: `http://127.0.0.1:5000/health`
- STT: `http://127.0.0.1:5001/health`

## Web 页面

默认访问：

```text
http://127.0.0.1:5000
```

页面包含：

- 文本合成
- 对话合成
- 语音转文本
- 历史记录

## API 简介

### 1. 文本合成

`POST /api/synthesize`

```json
{
  "text": "Q1\tHello world\t你好世界\nQ2\tHow are you?\t你好吗",
  "topic": "my_topic",
  "voice": "jenny",
  "rate": "+0%",
  "pitch": "+0Hz"
}
```

### 2. 对话合成

`POST /api/dialogue`

```json
{
  "text": "Mark: Hello.\nElena: Hi there.",
  "topic": "dialogue_topic",
  "maleVoice": "guy",
  "femaleVoice": "jenny",
  "rate": "+0%",
  "pitch": "+0Hz"
}
```

### 3. 语音转文本

`POST /api/stt`

表单字段：

- `file`
- `language`

### 4. 其他接口

- `GET /api/voices`
- `GET /api/sessions`
- `DELETE /api/sessions/{topic}`
- `GET /api/download/{topic}`
- `GET /api/download/{topic}/{file}`
- `GET /health`

## 支持的 MCP 工具

`mcp_server.py` 当前提供这些工具：

- `list_voices`
- `synthesize_text`
- `synthesize_dialogue`
- `list_sessions`
- `delete_session`
- `transcribe_file`
- `transcribe_url`

## MCP 启动

```bat
python mcp_server.py
```

## Claude Desktop / 其他 MCP Client 配置示例

如果本机 Python 在：

```text
C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe
```

可以这样配置：

```json
{
  "mcpServers": {
    "tts-stt": {
      "command": "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
      "args": [
        "D:\\语音合成\\mcp_server.py"
      ],
      "cwd": "D:\\语音合成",
      "env": {
        "MCP_TTS_BASE_URL": "http://127.0.0.1:5000",
        "MCP_STT_BASE_URL": "http://127.0.0.1:5001"
      }
    }
  }
}
```

## 跨电脑使用 MCP

可以，但推荐这样做：

### 服务机

- 启动 `web/server.py`
- 启动 `stt/server.py`
- 开放 `5000` 和 `5001` 端口

### 客户机

- 本地运行自己的 `mcp_server.py`
- 把 `MCP_TTS_BASE_URL` / `MCP_STT_BASE_URL` 指向服务机 IP

例如：

```json
{
  "mcpServers": {
    "tts-stt": {
      "command": "python",
      "args": [
        "D:\\your-local-copy\\mcp_server.py"
      ],
      "cwd": "D:\\your-local-copy",
      "env": {
        "MCP_TTS_BASE_URL": "http://192.168.1.25:5000",
        "MCP_STT_BASE_URL": "http://192.168.1.25:5001"
      }
    }
  }
}
```

## 备注

- 当前前端仍是单文件 React 页面，适合快速部署和内网使用
- 如果后续要做更复杂的前端迭代，建议再拆分为正式工程化结构
