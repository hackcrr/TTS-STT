# Deployment Notes

## 1. Environment variables

Copy `.env.example` to `.env` and adjust the values you need.

Key variables:

- `TTS_HOST` / `TTS_PORT`: bind address for the TTS web server
- `STT_HOST` / `STT_PORT`: bind address for the Whisper STT server
- `TTS_PUBLIC_BASE_URL`: optional public URL for the TTS web server
- `STT_PUBLIC_BASE_URL`: optional public URL for the STT server
- `STT_PUBLIC_HOST` / `STT_PUBLIC_SCHEME`: fallback public host/scheme when `STT_PUBLIC_BASE_URL` is empty
- `WHISPER_MODEL`: Whisper model name such as `small`, `medium`, `large`
- `MCP_TTS_BASE_URL` / `MCP_STT_BASE_URL`: target base URLs used by the MCP wrapper

## 2. How the frontend IP works now

The frontend no longer hardcodes a machine IP.

- TTS API: defaults to relative `/api`, so it follows the current browser host automatically
- STT API: defaults to `current-browser-host + STT_PORT`
- If you need a fixed external address, set `TTS_PUBLIC_BASE_URL` or `STT_PUBLIC_BASE_URL`

Examples:

```env
TTS_PORT=5000
STT_PORT=5001
```

If you open `http://192.168.1.25:5000`, the page will use:

- TTS: `http://192.168.1.25:5000/api`
- STT: `http://192.168.1.25:5001/api`

## 3. Start the services

Windows:

```bat
start.bat
```

Manual:

```bat
cd web
py -3 server.py
```

```bat
cd stt
py -3 server.py
```

## 4. MCP wrapper

The repo now includes `mcp_server.py`, a stdio MCP server that wraps the HTTP APIs.

Start it with:

```bat
py -3 mcp_server.py
```

Available MCP tools:

- `list_voices`
- `synthesize_text`
- `synthesize_dialogue`
- `list_sessions`
- `delete_session`
- `transcribe_file`
- `transcribe_url`

## 5. Example MCP client config

Example command:

```json
{
  "command": "py",
  "args": [
    "-3",
    "D:\\your-project\\mcp_server.py"
  ]
}
```

If your TTS/STT services are not running on the default ports, set `.env` first so the MCP wrapper can find them.
