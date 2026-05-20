# OpenClaw WebSocket 代理鉴权与集成方案 (WebSocket Proxy & Authentication Integration)

**文档版本**: v1.0.0
**更新日期**: 2026-04-01
**状态**: 已验证 (Verified)

---

## 1. 系统概述 (System Overview)

本方案旨在解决第三方自定义客户端（如基于 HTML/JS 的 Web 终端）无法直接与 OpenClaw 本地核心网关（Gateway）建立合法 WebSocket 连接的问题。

OpenClaw 核心网关在非 Web UI 模式下，强制要求客户端使用 Ed25519 椭圆曲线加密算法对设备连接请求进行签名认证（Device Identity / NOT_PAIRED）。由于在轻量级 Python 脚本或纯前端环境中复现此签名计算过程成本过高，本方案采用**子进程代理转发（Subprocess Proxy Forwarding）**策略，利用官方提供的命令行客户端（`openclaw tui`）作为“认证模块”，从而透明地接管并复用其高权限 WebSocket 通道。

## 2. 架构设计与请求链路 (Architecture & Request Flow)

本方案的核心思想是**职责分离**：官方 TUI 负责加密签名计算，Python 中间件负责网络路由与鉴权劫持，Web 前端负责用户交互。

### 2.1 拓扑结构

```mermaid
graph TD
    A[自定义 Web 前端 (HTML/JS)] -->|WebSocket (ws://127.0.0.1:20000/ws)| B(Python 代理桥接器)
    C[官方客户端 (openclaw tui)] -->|WebSocket (ws://127.0.0.1:20000/)| B
    B -->|透明转发与劫持 (ws://127.0.0.1:18789)| D[OpenClaw 核心网关]
```

### 2.2 鉴权劫持时序

1.  **代理服务启动**: Python 脚本（`bridge.py`）启动，监听本地 `20000` 端口。
2.  **唤醒认证模块**: Python 脚本在后台作为子进程启动官方客户端：`openclaw tui --url ws://127.0.0.1:20000 --password <YOUR_PWD>`。
    * *注意：此时官方客户端被重定向，去连接我们的 Python 代理，而不是真实的 OpenClaw 核心。*
3.  **计算加密签名**: 官方客户端读取本地私钥，计算出包含 `device.signature` 的合法 JSON 鉴权包，发送至 `20000` 端口。
4.  **透明转发与放行**: Python 代理截获该鉴权包，原封不动地转发至真实的 OpenClaw 核心网关（`18789` 端口）。核心网关验证签名通过，建立拥有 `operator.write` 权限的黄金通道。
5.  **前端接入与劫持**: Web 前端通过 WebSocket 连接至代理的 `/ws` 路径。代理拦截前端发送的指令文本，封装成官方要求的 JSON 格式（包含 `sessionKey` 和防重发 `idempotencyKey`），通过已验证的通道发送给核心网关。核心网关的响应则由代理分发回前端。

## 3. 环境依赖与复现步骤 (Environment & Reproduction Steps)

### 3.1 前置条件

* 已全局安装并配置好 OpenClaw CLI（能够在终端中运行 `openclaw tui`）。
* 已安装 Python 3.8+ 环境。
* 已安装 `aiohttp` 库：`pip install aiohttp`。
* 确认 OpenClaw 核心网关运行在默认端口 `18789`。

### 3.2 核心代码实现：寄生桥接器 (bridge.py)

创建并保存以下 Python 脚本为 `bridge.py`。这是实现上述架构的核心中间件。

```python
import asyncio
import json
import subprocess
import uuid
import os
import sys
from aiohttp import web, ClientSession, WSMsgType

# --- 配置区域 ---
TARGET_URL = os.environ.get("OC_WS_URL", "ws://127.0.0.1:18789")
OC_PASSWORD = os.environ.get("OC_PASSWORD", "")
# --------------

ui_websockets = set()
brain_ws = None

async def root_handler(request):
    """根路径路由：处理 TUI 的连接请求或返回 Web UI 页面"""
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return await dongle_ws_handler(request)
    
    ui_file = "openclaw-chat.html"
    if os.path.exists(ui_file):
        return web.FileResponse(ui_file)
    return web.Response(text=f"找不到 {ui_file}", status=404)

async def ui_ws_handler(request):
    """处理前端 Web UI 的 WebSocket 接入与消息分发"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    ui_websockets.add(ws)
    print("🖥️  [前端 UI] 已接入寄生桥接器！")
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                global brain_ws
                if brain_ws and not brain_ws.closed:
                    # 按照官方 RequestFrameSchema 封装消息
                    payload = {
                        "type": "req",
                        "id": str(uuid.uuid4()),
                        "method": "chat.send",
                        "params": {
                            "sessionKey": "agent:main:main",
                            "message": msg.data,
                            "deliver": False,
                            "idempotencyKey": str(uuid.uuid4())
                        }
                    }
                    await brain_ws.send_str(json.dumps(payload))
                    print(f"✉️  [指令注入] 发送至大脑: {msg.data}")
                else:
                    await ws.send_str(json.dumps({"type": "error", "content": "认证模块未就绪！"}))
    finally:
        ui_websockets.remove(ws)
        print("🖥️  [前端 UI] 连接已断开。")
    return ws

async def dongle_ws_handler(request):
    """接管官方 TUI，透明转发其带有加密签名的鉴权请求"""
    global brain_ws
    print("🔑 [认证模块] 官方 TUI 进程已上线，引导加密握手...")
    
    client_ws = web.WebSocketResponse(protocols=("openclaw-v1",))
    await client_ws.prepare(request)

    # 过滤不兼容的 Headers
    headers_to_forward = {k: v for k, v in request.headers.items() if k.lower() not in ['host', 'upgrade', 'connection', 'sec-websocket-key', 'sec-websocket-version', 'sec-websocket-extensions']}

    try:
        async with ClientSession() as session:
            async with session.ws_connect(TARGET_URL, headers=headers_to_forward, protocols=("openclaw-v1",)) as server_ws:
                brain_ws = server_ws
                print("✅ [系统核心] 成功夺取高权限 WebSocket 通道！")

                async def client_to_server():
                    async for msg in client_ws:
                        if msg.type == WSMsgType.TEXT:
                            await server_ws.send_str(msg.data)
                        elif msg.type == WSMsgType.ERROR:
                            break

                async def server_to_client():
                    async for msg in server_ws:
                        if msg.type == WSMsgType.TEXT:
                            # 必须向 TUI 转发以维持其存活状态
                            await client_ws.send_str(msg.data)
                            
                            try:
                                parsed = json.loads(msg.data)
                                # 过滤系统心跳包
                                if parsed.get("event") not in ["tick", "heartbeat", "presence", "health", "pong"]:
                                    # 广播系统响应给所有 Web UI
                                    for ui_ws in ui_websockets:
                                        await ui_ws.send_str(json.dumps({"type": "reply", "content": msg.data}))
                            except:
                                pass
                        elif msg.type == WSMsgType.ERROR:
                            break

                await asyncio.gather(client_to_server(), server_to_client())
    except Exception as e:
        print(f"❌ [系统错误] 桥接中断: {e}")
    finally:
        brain_ws = None
        
    return client_ws

async def start_background_tasks(app):
    """作为子进程唤醒官方 TUI"""
    print("🚀 正在后台唤醒官方 TUI 认证模块...")
    kwargs = {}
    
    # [避坑指南]: Windows 环境下通过 npm 安装的全局命令为 .cmd 批处理文件
    executable = "openclaw.cmd" if sys.platform == 'win32' else "openclaw"
    
    # 独立控制台运行，防止污染当前终端日志 (Windows only)
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NEW_CONSOLE
        
    try:
        app['tui_process'] = subprocess.Popen(
            [executable, "tui", "--url", "ws://127.0.0.1:20000", "--password", OC_PASSWORD],
            **kwargs
        )
    except FileNotFoundError:
        print(f"❌ 启动失败！找不到 {executable}。")

async def cleanup_background_tasks(app):
    if 'tui_process' in app:
        print("🛑 正在终止后台认证模块...")
        app['tui_process'].terminate()

app = web.Application()
app.router.add_get('/', root_handler)
app.router.add_get('/ws', ui_ws_handler)

app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)

if __name__ == '__main__':
    print("=" * 60)
    print("🕸️  OpenClaw 代理桥接器 (Proxy Bridge) 已启动")
    print("👉 请在浏览器访问: http://localhost:20000")
    print("=" * 60)
    web.run_app(app, host='0.0.0.0', port=20000)
```

### 3.3 运行流程

1.  将上述 `bridge.py` 与你的 Web 前端文件（`openclaw-chat.html`）放置在同一目录下。
2.  在终端中执行命令：
    ```bash
    python bridge.py
    ```
3.  **预期表现**：
    * 主终端将显示桥接器启动日志。
    * (仅限 Windows) 系统将弹出一个新的控制台窗口，运行官方的 TUI 界面（请勿关闭该窗口，它是签名的计算核心）。
    * 主终端出现提示：`✅ [系统核心] 成功夺取高权限 WebSocket 通道！`
4.  打开浏览器，访问 `http://localhost:20000`，即可通过 Web 界面与 OpenClaw 系统进行高权限对话。

## 4. 常见问题排查 (Troubleshooting)

* **问题 1**: 启动时提示 `WinError 2: 系统找不到指定的文件`。
    * **原因**: Python 的 `subprocess` 模块在 Windows 下无法直接识别无后缀的 npm 全局包。
    * **解决**: 方案已在代码 `start_background_tasks` 中通过判断系统平台并强制指定 `openclaw.cmd` 后缀来解决。
* **问题 2**: 消息无法发送，提示认证模块未就绪。
    * **原因**: 弹出的官方 TUI 窗口可能被意外关闭，导致鉴权通道断开。
    * **解决**: 重启 `bridge.py` 服务。