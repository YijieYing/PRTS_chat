# PRTS Chat Bridge

一个基于 WebSocket 代理的桌面聊天客户端，将终端风格 Web UI 桥接到 OpenClaw AI 网关，并集成任务管理系统（DDL Manager）。

## 功能

- **实时对话**：通过 WebSocket 与 OpenClaw AI 网关双向通信
- **终端风格 UI**：可拖拽、无边框、透明背景的赛博朋克风桌面窗口
- **任务管理**：内置 DDL 管理器，支持截止日期倒计时、优先级排序、每日重置、拖拽排序
- **图片附件**：支持从浏览器发送图片到 AI 对话
- **AI 联动**：AI 可以直接通过 `add_ddl` / `toggle_ddl` 等接口管理你的任务

## 架构

```
浏览器 Web UI ←→ aiohttp 代理 (bridge.py) ←→ OpenClaw 网关 (18789)
                      ↓
               pywebview 桌面窗口 (20000)
```

- **bridge.py** — 核心中间件，维护上游（网关）和下游（UI）两个 WebSocket 通道，管理设备认证
- **openclaw-chat.html** — 终端风格聊天界面，连接 `/ws` 收发消息
- **ddl_manager.py** — 任务/DDL 管理引擎，持久化到 JSON 文件
- **prts.py** — 独立的任务管理窗口（可单独运行）
- **device.py** — 设备身份模块

## 安装与运行

### 前置条件

- Python 3.8+
- 已安装 OpenClaw CLI（可运行 `openclaw tui`）
- OpenClaw 核心网关运行在默认端口 `18789`

### 步骤

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 设置环境变量（可选，默认连接本地网关）
set OC_WS_URL=ws://127.0.0.1:18789
set OC_PASSWORD=your_password_here

# 3. 启动
python bridge.py
# 或
run.bat
```

启动后会自动打开桌面窗口，访问地址 `http://localhost:20000`。

### 单独运行任务管理窗口

```bash
python prts.py
```

## 任务管理（DDL Manager）

在聊天窗口的任务面板中可以管理待办事项：

| 输入格式 | 说明 |
|---------|------|
| `任务内容` | 添加普通任务 |
| `任务内容 /MMDD` | 添加带截止日期的任务（月/日） |
| `任务内容 /MMDDHH` | 带截止时间的任务（月/日/时） |
| `任务内容 \N` | 插入到第 N 个优先级位置 |

任务面板支持两种视图：
- **PRIORITY_QUEUE** — 手动排序模式，可拖拽调整顺序
- **DDL_COUNTDOWN** — 按截止日期排序，过期任务红色高亮

## 协议

消息使用 OpenClaw `RequestFrameSchema` 格式：

```json
{
  "type": "req",
  "id": "uuid",
  "method": "chat.send",
  "params": {
    "sessionKey": "agent:main:main",
    "message": "...",
    "deliver": true,
    "idempotencyKey": "uuid"
  }
}
```

网关响应（心跳/系统事件除外）广播给所有已连接的 UI 客户端。

## 配置

| 环境变量 | 默认值 | 说明 |
|---------|-------|------|
| `OC_WS_URL` | `ws://127.0.0.1:18789` | OpenClaw 网关地址 |
| `OC_PASSWORD` | 空 | 网关认证密码 |

设备认证令牌从 `~/.openclaw/identity/device-auth.json` 自动读取。
