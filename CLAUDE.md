# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

PRTS Chat Bridge is a desktop chat application that wraps an OpenClaw AI agent gateway inside a pywebview window. It uses aiohttp for WebSocket proxying between the web UI and the OpenClaw gateway, and includes a task management system (DDL Manager) accessible from both the UI and the AI agent.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bridge (starts aiohttp server on port 20000 + pywebview desktop window)
python bridge.py
# or on Windows
run.bat
```

Server runs at `http://localhost:20000`. The pywebview desktop window opens automatically.

## Architecture

### bridge.py — Main entry point and WebSocket proxy

Two WebSocket roles via **aiohttp** (not FastAPI):

1. **Upstream (dongle)**: When a browser connects on `/` with `Upgrade: websocket`, it proxies bidirectionally to the OpenClaw gateway at `ws://127.0.0.1:18789`, injecting device auth tokens.
2. **Downstream**: Browser connections to `/ws` receive forwarded gateway responses and send user messages to the gateway.

Also spawns an `openclaw tui` subprocess for authentication on startup, and creates a pywebview desktop window with frameless transparent Chromium.

Key globals: `brain_ws` (upstream connection), `ui_websockets` (downstream clients).

### ddl_manager.py — Task/DDL management engine

`DDLManager` class that persists tasks to `prts_archive.json`. Supports:
- Tasks with optional deadlines (DDL timestamps in ms) and daily recurring reset
- Priority ordering and completion logging
- Disk sync on every operation to prevent data loss when both the UI and AI agent modify tasks

Exposed to the pywebview JS API via `bridge.py:Api` (methods: `get_ddls`, `add_ddl`, `toggle_ddl`, `delete_ddl`).

### prts.py — Standalone task manager window

A separate pywebview app with its own embedded HTML/JS UI. Independent from bridge.py — has its own `Api` class and reads/writes the same `prts_archive.json`. Run standalone with `python prts.py`.

### device.py — Device identity

Provides a persistent device ID (stored in `.device_id`) and signature generation for OpenClaw gateway authentication.

### openclaw-chat.html — Terminal-styled chat UI

Draggable, frameless web UI with Cyberpunk/PRTS aesthetic. Connects to `ws://localhost:20000/ws`, supports text messages and image attachments (base64-encoded).

## Configuration

In `bridge.py`:
- `TARGET_URL` (line ~45) — OpenClaw gateway WebSocket address (default `ws://127.0.0.1:18789`)
- `OC_PASSWORD` — Gateway authentication password
- Device auth token loaded from `~/.openclaw/identity/device-auth.json`

## Protocol

Messages to the gateway use OpenClaw `RequestFrameSchema`: `{"type": "req", "id", "method": "chat.send", "params": {"sessionKey", "message", "deliver": true}}`. Gateway responses (excluding heartbeat/tick events) are broadcast to all connected UI clients.

## Data files

- `prts_archive.json` — Shared task data (tasks array + completion logs by date)
- `.device_id` — Persistent device UUID
- `temp_attachments/` — Temporary storage for uploaded images
