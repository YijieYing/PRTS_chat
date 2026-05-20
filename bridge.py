import os
import tempfile
import uuid
import base64

# 1. 强制 Chromium 铺设完全透明的底漆
os.environ["WEBVIEW2_DEFAULT_BACKGROUND_COLOR"] = "00000000"

# 🚀 附件临时目录
ATTACHMENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_attachments")
os.makedirs(ATTACHMENT_DIR, exist_ok=True)


def save_attachment(base64_data: str, filename: str, mime_type: str = "image/png") -> str:
    """将 base64 附件保存到临时文件，返回文件绝对路径。"""
    ext_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    ext = ext_map.get(mime_type, ".bin")
    unique_name = f"{uuid.uuid4().hex[:12]}_{filename}{ext}"
    filepath = os.path.join(ATTACHMENT_DIR, unique_name)
    with open(filepath, "wb") as f:
        f.write(base64.b64decode(base64_data))
    return filepath

# 2. 随机缓存：保证每次启动都是干净的"第一次"
temp_cache_dir = os.path.join(tempfile.gettempdir(), f"openclaw_{uuid.uuid4().hex[:8]}")
os.environ["WEBVIEW2_USER_DATA_FOLDER"] = temp_cache_dir

import asyncio
import json
import subprocess
import sys
import threading
import webview
from aiohttp import web, ClientSession, WSMsgType

# 🚀 引入我们的数据引擎
from ddl_manager import DDLManager

TARGET_URL = os.environ.get("OC_WS_URL", "ws://127.0.0.1:18789")
OC_PASSWORD = os.environ.get("OC_PASSWORD", "")

# 🔑 device token 路径
DEVICE_AUTH_PATH = os.path.expanduser("~/.openclaw/identity/device-auth.json")


def load_device_token():
    """从 ~/.openclaw/identity/device-auth.json 读取 operator token。失败返回 None。"""
    try:
        with open(DEVICE_AUTH_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 结构是 tokens.operator.token
            token = data.get("tokens", {}).get("operator", {}).get("token")
            if token:
                print(f"🔑 [auth] 已加载 device token: {token[:24]}...")
            else:
                print(f"⚠️ [auth] device-auth.json 里没有 tokens.operator.token")
            return token
    except Exception as e:
        print(f"⚠️ [auth] 读取 device-auth.json 失败: {e}")
        return None


ui_websockets = set()
brain_ws = None
_app = None

class Api:
    def __init__(self):
        # 初始化 DDL 管理器
        try:
            self.ddl = DDLManager()
        except Exception as e:
            print(f"DDLManager 初始化失败: {e}")
            self.ddl = None

    def minimize(self):
        w = webview.windows[0]
        # 🚀 最小化补丁：在最小化前，先把它流放到屏幕外！
        # 这样它唤醒的时候也会在屏幕外重绘，避开白斑
        w.move(-20000, -20000)
        w.minimize()

    def toggle_maximize(self):
        """🚀 终极流放魔法 + 自动居中归位"""
        w = webview.windows[0]
        if not hasattr(self, '_maximized'):
            # 记录默认尺寸
            self._orig_w = 860
            self._orig_h = 680
            self._maximized = False

        import time
        screen = webview.screens[0]
        
        if not self._maximized:
            # 放大前，记录当前实际大小
            self._orig_w = w.width
            self._orig_h = w.height
            
            tx, ty = 1, 1
            tw, th = screen.width - 2, screen.height - 40
            
            # 1. 瞬移到屏幕外
            w.move(-20000, -20000)
            # 2. 变形
            w.resize(tw, th)
            # 3. 等待重绘
            time.sleep(0.25)
            # 4. 回归屏幕
            w.move(tx, ty)
            self._maximized = True
        else:
            # 还原时：先流放到屏幕外
            w.move(-20000, -20000)
            # 缩回原来的小尺寸
            w.resize(self._orig_w, self._orig_h)
            # 等待 GPU 重新铺设透明通道
            time.sleep(0.25)
            
            # 🌟 稳妥的居中算法
            screen = webview.screens[0]
            actual_w = w.width
            actual_h = w.height
            
            cx = int((screen.width - actual_w) / 2) - 40
            cy = int((screen.height - actual_h) / 2) - 60
            
            w.move(cx, cy)
            self._maximized = False
            
        return self._maximized

    # 🚀 --- 新增 DDL 相关的 API 供前端调用 ---
    def get_ddls(self):
        """获取所有任务和侧边栏统计信息"""
        if not self.ddl: return {"tasks": [], "summary": {"danger":0, "warning":0, "safe":0}}
        return {"tasks": self.ddl.get_all_tasks(), "summary": self.ddl.get_sidebar_summary()}
        
    def toggle_ddl(self, task_id):
        """切换完成状态"""
        if self.ddl: self.ddl.toggle_task(task_id)
        return self.get_ddls()
        
    def delete_ddl(self, task_id):
        """删除任务"""
        if self.ddl: self.ddl.delete_task(task_id)
        return self.get_ddls()
        
    def add_ddl(self, text, ddl_time=None, recurring=False):
        """添加新任务（未来供大模型直接调用）"""
        if self.ddl: self.ddl.add_task(text, ddl_time, recurring=recurring)
        return self.get_ddls()

    def shutdown(self):
        print("🛑 正在终止进程...")
        if _app and 'tui_process' in _app and _app['tui_process']:
            proc = _app['tui_process']
            if sys.platform == 'win32':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.terminate()
        if webview.windows:
            webview.windows[0].destroy()
        os._exit(0)
        
# ─────────────────────────────────────────────
#  aiohttp Handlers (回归至简大道)
# ─────────────────────────────────────────────

async def root_handler(request):
    print(f"[root_handler] 收到请求: method={request.method} path={request.path} upgrade={request.headers.get('Upgrade', 'none')} ua={request.headers.get('User-Agent', 'none')}")
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return await dongle_ws_handler(request)
    ui_file = "openclaw-chat.html"
    if os.path.exists(ui_file):
        return web.FileResponse(ui_file)
    return web.Response(text=f"找不到 {ui_file}", status=404)

async def ui_ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    ui_websockets.add(ws)
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                global brain_ws
                if brain_ws and not brain_ws.closed:
                    import time
                    
                    # 🚀 尝试解析 JSON（支持附件消息）
                    try:
                        parsed = json.loads(msg.data)
                    except json.JSONDecodeError:
                        parsed = None
                    
                    final_message = msg.data  # 默认：原文发送
                    
                    # 处理附件消息 (增加 isinstance 判定，极其重要！)
                    if parsed and isinstance(parsed, dict) and parsed.get("type") == "attachment":
                        try:
                            filepath = save_attachment(
                                parsed["data"],
                                parsed.get("filename", "file"),
                                parsed.get("mimeType", "image/png")
                            )
                            # 组合文本消息 + 图片路径提示
                            text_part = parsed.get("text", "").strip()
                            if text_part:
                                final_message = f"{text_part}\n\n[本地图片: {filepath}]"
                            else:
                                final_message = f"[本地图片: {filepath}]"
                            print(f"[{time.time():.3f}] [BRIDGE] 保存附件: {filepath}")
                        except Exception as e:
                            print(f"[BRIDGE] 附件保存失败: {e}")
                            final_message = f"[附件处理失败] {str(e)}"
                    else:
                        print(f"[{time.time():.3f}] [UI -> BRIDGE] 发送至网关: {msg.data}")
                    
                    # 🚀 唯一真正解决积压的设定：deliver: True
                    payload = {
                        "type": "req", 
                        "id": str(uuid.uuid4()), 
                        "method": "chat.send", 
                        "params": {
                            "sessionKey": "agent:main:main", 
                            "message": final_message, 
                            "deliver": True, 
                            "idempotencyKey": str(uuid.uuid4())
                        }
                    }
                    # 直接 await，回归稳定线性执行，抛弃复杂的锁
                    await brain_ws.send_str(json.dumps(payload))
                else:
                    error_msg = {"type": "error", "content": "[GATEWAY_OFFLINE] 无法连接到 OpenClaw 核心网关 (18789)！请检查大模型后台服务是否已启动。"}
                    await ws.send_str(json.dumps(error_msg))
                    
    finally:
        ui_websockets.remove(ws)
    return ws

async def dongle_ws_handler(request):
    global brain_ws
    client_ws = web.WebSocketResponse(protocols=("openclaw-v1",))
    await client_ws.prepare(request)
    
    # 🔑 每次握手都重新读 token（万一中途轮换了）
    auth_token = load_device_token()
    
    # 转发 UI 来的 headers，剥掉 hop-by-hop / WebSocket 内部头
    headers_to_forward = {k: v for k, v in request.headers.items() 
                          if k.lower() not in ['host', 'upgrade', 'connection', 
                          'sec-websocket-key', 'sec-websocket-version', 'sec-websocket-extensions',
                          'authorization']}  # 也剥掉旧的 authorization，避免冲突
    
    # 🔑 注入 device token，让 gateway 接受连接
    if auth_token:
        headers_to_forward['Authorization'] = f'Bearer {auth_token}'
    else:
        print("⚠️ [bridge] 没有 device token，连接 gateway 大概率被拒")
    
    try:
        async with ClientSession(trust_env=False) as session:
            try:
                async with session.ws_connect(
                    TARGET_URL, 
                    headers=headers_to_forward, 
                    protocols=("openclaw-v1",), 
                    heartbeat=15.0, 
                    proxy=None
                ) as server_ws:
                    brain_ws = server_ws
                    print("✅ [系统核心] 成功连接真实网关 18789！")
                    stop = asyncio.Event()
                    
                    async def client_to_server():
                        try:
                            async for msg in client_ws:
                                if stop.is_set(): break
                                if msg.type == WSMsgType.TEXT: 
                                    await server_ws.send_str(msg.data)
                                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE): 
                                    break
                        finally:
                            stop.set()
                                
                    async def server_to_client():
                        try:
                            async for msg in server_ws:
                                if stop.is_set(): break
                                if msg.type == WSMsgType.TEXT:
                                    try:
                                        await client_ws.send_str(msg.data)
                                    except Exception:
                                        pass
                                    try:
                                        parsed = json.loads(msg.data)
                                        if parsed.get("event") not in ["tick", "heartbeat", "presence", "health", "pong"]:
                                            for ui_ws in list(ui_websockets): 
                                                if not ui_ws.closed:
                                                    await ui_ws.send_str(json.dumps({"type": "reply", "content": msg.data}))
                                    except Exception: 
                                        pass
                                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE): 
                                    break
                        finally:
                            stop.set()
                                
                    await asyncio.gather(client_to_server(), server_to_client(), return_exceptions=True)
                    
            except Exception as e:
                print(f"❌ [连接失败] {type(e).__name__}: {e}")
    except Exception as e: 
        print(f"Dongle error: {e}")
    finally: 
        brain_ws = None
        print("🛑 [系统核心] 桥接已断开。")
    return client_ws


async def start_background_tasks(app):
    await asyncio.sleep(2)
    executable = "openclaw.cmd" if sys.platform == 'win32' else "openclaw"
    
    # 🔑 读 device token 给 TUI 用
    tui_token = load_device_token()
    if not tui_token:
        print("❌ [TUI] 没有 token，TUI 无法启动")
        return
    
    try:
        app['tui_process'] = subprocess.Popen(
            [executable, "tui", "--url", "ws://127.0.0.1:20000", "--token", tui_token],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        def read_output():
            for line in app['tui_process'].stdout:
                print(f"[TUI] {line.rstrip()}")
        threading.Thread(target=read_output, daemon=True).start()
        print("🚀 [TUI] 已启动认证模块")
    except FileNotFoundError:
        print("❌ 找不到 openclaw 命令")

async def cleanup_background_tasks(app):
    if 'tui_process' in app: app['tui_process'].terminate()

def run_server():
    global _app
    _app = web.Application()
    _app.router.add_get('/', root_handler)
    _app.router.add_get('/ws', ui_ws_handler)
    _app.on_startup.append(start_background_tasks)
    _app.on_cleanup.append(cleanup_background_tasks)
    web.run_app(_app, host='0.0.0.0', port=20000, print=None, access_log=None)

# 🌟 黄金起步法则：在暗处渲染，熟透后再空降屏幕视觉中心
def on_loaded():
    import threading
    def _center_window():
        import time
        # 睡 0.2 秒，确保 Chromium 已经在屏幕外把透明图层彻底铺满
        time.sleep(0.2) 
        try:
            w = webview.windows[0]
            screen = webview.screens[0]
            actual_w = w.width
            actual_h = w.height
            cx = int((screen.width - actual_w) / 2) - 40
            cy = int((screen.height - actual_h) / 2) - 60
            w.move(cx, cy)
        except Exception:
            pass
    threading.Thread(target=_center_window, daemon=True).start()

# 🌟 唤醒恢复拦截：从任务栏恢复时，给 GPU 时间重新铺设透明层
def on_restored():
    import threading
    def _restore_hack():
        import time
        time.sleep(0.25) # 依然在屏幕外暗处（因为我们最小化前将它流放了）
        try:
            w = webview.windows[0]
            screen = webview.screens[0]
            actual_w = w.width
            actual_h = w.height
            cx = int((screen.width - actual_w) / 2) - 40
            cy = int((screen.height - actual_h) / 2) - 60
            w.move(cx, cy) # 带着透亮的质感回到中心！
        except Exception:
            pass
    threading.Thread(target=_restore_hack, daemon=True).start()

if __name__ == '__main__':
    import threading
    _server_thread = threading.Thread(target=run_server, daemon=True)
    _server_thread.start()
    
    import time
    time.sleep(1.5)

    window = webview.create_window(
        'SYS.TERMINAL // OPENCLAW',
        'http://127.0.0.1:20000',
        frameless=True,
        transparent=True,
        hidden=False,
        x=-20000,
        y=-20000,
        width=860,
        height=680,
        min_size=(400, 340),
        resizable=True,
        js_api=Api()
    )
    
    # 绑定两个关键生命周期事件
    window.events.loaded += on_loaded
    window.events.restored += on_restored
    
    webview.start(debug=False)