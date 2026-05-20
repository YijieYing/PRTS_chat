import webview
import json
import os

# ====== 确保路径绝对定位 ======
current_dir = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(current_dir, "prts_archive.json")
# ==========================

class Api:
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Read error: {e}")
        return {"tasks": [], "logs": {}}

    def save_data(self, data):
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"Save error: {e}")
            return False

    def close_window(self):
        import webview
        webview.windows[0].destroy()

# 注意这里的 r"""，它让 Python 不再瞎转义内部的 JS 代码
html_content = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PRTS // DIRECTIVES</title>
    <style>
        :root {
            --bg-color: transparent;
            --panel-bg: #1e1e1ecc;   
            --ak-yellow: #f7c513;
            --text-main: #f0f0f0;
            --text-dim: #888888;
            --danger: #ff4d4f;
            --safe: #52c41a;
            --font-mono: 'Courier New', Courier, monospace;
        }

        html, body {
            margin: 0; padding: 0; width: 100vw; height: 100vh;
            background-color: transparent; overflow: hidden;
            font-family: var(--font-mono); color: var(--text-main);
        }

        .terminal-window {
            width: 100%; height: 100%; background-color: var(--panel-bg);
            border: 1px solid #333; box-sizing: border-box;
            clip-path: polygon(0 0, 100% 0, 100% calc(100% - 25px), calc(100% - 25px) 100%, 0 100%);
            display: flex; flex-direction: column; position: relative;
            background-image: linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
            background-size: 20px 20px; backdrop-filter: blur(5px);
        }

        .terminal-window::before {
            content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 4px;
            background-color: var(--ak-yellow); z-index: 10;
        }

        header { padding: 20px 20px 10px 20px; user-select: none; -webkit-app-region: drag; }

        .sys-info { font-size: 0.75rem; color: var(--text-dim); display: flex; justify-content: space-between; margin-bottom: 5px; }
        .time-display { color: var(--ak-yellow); font-weight: bold; letter-spacing: 1px; }
        h1 { margin: 0; font-size: 1.5rem; text-transform: uppercase; letter-spacing: 2px; color: var(--ak-yellow); text-shadow: 0 0 5px rgba(247, 197, 19, 0.3); }

        .sort-tabs {
            display: flex; padding: 0 20px; border-bottom: 1px dashed #444; margin-bottom: 10px;
        }
        .tab {
            font-size: 0.8rem; padding: 5px 15px; cursor: pointer; color: var(--text-dim);
            transition: all 0.2s; border-bottom: 2px solid transparent; user-select: none;
        }
        .tab.active { color: var(--ak-yellow); border-bottom-color: var(--ak-yellow); }
        .tab:hover:not(.active) { color: #fff; }

        .task-container { padding: 0 20px 20px 20px; flex-grow: 1; overflow-y: auto; }
        .task-container::-webkit-scrollbar { width: 4px; }
        .task-container::-webkit-scrollbar-thumb { background: var(--ak-yellow); }

        .task-list { list-style: none; padding: 0; margin: 0; }
        .task-item {
            display: flex; align-items: center; padding: 8px 10px;
            background-color: rgba(0, 0, 0, 0.3); border-left: 3px solid transparent; margin-bottom: 8px;
            transition: all 0.2s ease; position: relative;
        }
        .task-item:hover { border-left-color: var(--ak-yellow); background-color: rgba(255, 255, 255, 0.05); }
        
        .task-item.draggable { cursor: grab; }
        .task-item.draggable:active { cursor: grabbing; }
        .task-item.drag-over { border-top: 2px solid var(--ak-yellow); }
        
        .drag-handle { color: #444; margin-right: 10px; font-size: 0.8rem; user-select: none; }
        .task-item:hover .drag-handle { color: var(--ak-yellow); }

        .task-item.completed { opacity: 0.5; border-left-color: var(--text-dim); }
        .task-item.completed .task-text { text-decoration: line-through; color: var(--text-dim); }

        .checkbox {
            width: 14px; height: 14px; border: 1px solid var(--ak-yellow); margin-right: 12px;
            cursor: pointer; display: flex; justify-content: center; align-items: center;
        }
        .task-item.completed .checkbox { background-color: var(--ak-yellow); border-color: var(--ak-yellow); }

        .task-text { flex-grow: 1; font-size: 0.9rem; user-select: none; pointer-events: none; }
        
        .ddl-badge {
            font-size: 0.7rem; padding: 2px 6px; background: rgba(255, 255, 255, 0.1);
            border-radius: 2px; margin-right: 10px; color: var(--text-dim); transition: 0.3s;
        }
        .ddl-badge.danger { background: rgba(255, 77, 79, 0.2); color: var(--danger); border: 1px solid var(--danger); }

        .delete-btn { background: none; border: none; color: var(--danger); cursor: pointer; font-weight: bold; opacity: 0; transition: opacity 0.2s; }
        .task-item:hover .delete-btn { opacity: 1; }

        .input-group { display: flex; padding: 15px; background-color: rgba(0, 0, 0, 0.4); border-top: 1px solid #333; }
        input[type="text"] { flex-grow: 1; background: transparent; border: 1px solid #444; color: var(--text-main); padding: 10px; font-family: var(--font-mono); outline: none; }
        input[type="text"]:focus { border-color: var(--ak-yellow); box-shadow: inset 0 0 5px rgba(247, 197, 19, 0.2); }
        button.add-btn { background-color: var(--ak-yellow); color: #000; border: none; padding: 0 15px; font-weight: bold; cursor: pointer; margin-left: 10px; transition: 0.2s; }
        button.add-btn:hover { background-color: #fff; }

        .close-app-btn { position: absolute; top: 10px; right: 15px; background: transparent; border: none; color: var(--text-dim); font-size: 1.2rem; cursor: pointer; z-index: 20; -webkit-app-region: no-drag; }
        .close-app-btn:hover { color: var(--danger); }
    </style>
</head>
<body>
    <div class="terminal-window">
        <button class="close-app-btn" onclick="pywebview.api.close_window()">×</button>
        <header>
            <div class="sys-info">
                <span>SYS.ONLINE</span>
                <span><span id="current-date">0000.00.00</span> <span class="time-display" id="current-time">00:00:00</span></span>
            </div>
            <h1>DAILY_DIRECTIVES</h1>
        </header>

        <div class="sort-tabs">
            <div class="tab active" id="tab-priority" onclick="setMode('priority')">PRIORITY_QUEUE</div>
            <div class="tab" id="tab-ddl" onclick="setMode('ddl')">DDL_COUNTDOWN</div>
        </div>
        
        <div class="task-container">
            <ul class="task-list" id="task-list">
                <li style="color: var(--text-dim); font-size: 0.8rem;">[SYS] CONNECTING TO ARCHIVE...</li>
            </ul>
        </div>

        <div class="input-group">
            <input type="text" id="task-input" placeholder="INPUT: task /MMDDHH or task \N" autocomplete="off">
            <button class="add-btn" id="add-btn">EXEC</button>
        </div>
    </div>

    <script>
        let tasks = []; 
        let logs = {};
        let currentMode = 'priority'; 
        let draggedItemId = null;

        function getTodayString() { const d = new Date(); return `${d.getFullYear()}.${String(d.getMonth()+1).padStart(2,'0')}.${String(d.getDate()).padStart(2,'0')}`; }
        function getTimeString() { const d = new Date(); return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`; }
        
        // 修复1：不再全屏刷新打断拖拽，只精准更新时间和徽章颜色
        setInterval(() => { 
            document.getElementById('current-time').textContent = getTimeString(); 
            const now = Date.now();
            document.querySelectorAll('.ddl-badge').forEach(badge => {
                const ts = parseInt(badge.dataset.time);
                if (ts && ts < now) badge.classList.add('danger');
            });
        }, 1000);

        async function saveData() { if (window.pywebview && pywebview.api) await pywebview.api.save_data({ tasks, logs }); }

        function setMode(mode) {
            currentMode = mode;
            document.getElementById('tab-priority').className = `tab ${mode === 'priority' ? 'active' : ''}`;
            document.getElementById('tab-ddl').className = `tab ${mode === 'ddl' ? 'active' : ''}`;
            renderTasks();
        }

        function parseInput(rawText) {
            let text = rawText.trim();
            let isDDL = false, isPriority = false;
            let ddlTime = null;
            let targetIndex = tasks.length;

            // 修复2：完美避开转义冲突的正则解析
            const prioMatch = text.match(/\s*\\(\d+)$/);
            const ddlMatch = text.match(/\s*\/(\d{4}|\d{6})$/);

            if (prioMatch) {
                isPriority = true;
                text = text.replace(prioMatch[0], '');
                let n = parseInt(prioMatch[1]);
                targetIndex = Math.max(0, Math.min(n - 1, tasks.length));
            } 
            else if (ddlMatch) {
                isDDL = true;
                text = text.replace(ddlMatch[0], '');
                const nums = ddlMatch[1];
                const now = new Date();
                let mm = parseInt(nums.substring(0, 2)) - 1;
                let dd = parseInt(nums.substring(2, 4));
                let hh = nums.length === 6 ? parseInt(nums.substring(4, 6)) : 23;
                let min = nums.length === 6 ? 0 : 59;
                
                let yyyy = now.getFullYear();
                if (mm < now.getMonth() - 1) yyyy += 1; 

                ddlTime = new Date(yyyy, mm, dd, hh, min).getTime();
            }

            return { text, isPriority, targetIndex, isDDL, ddlTime };
        }

        function addTask() {
            try {
                const input = document.getElementById('task-input');
                const raw = input.value;
                if (!raw.trim()) return;

                const parsed = parseInput(raw);
                
                const newTask = {
                    id: Date.now(),
                    text: parsed.text,
                    completed: false,
                    ddl: parsed.ddlTime
                };

                if (parsed.isPriority) {
                    tasks.splice(parsed.targetIndex, 0, newTask);
                    setMode('priority');
                } else if (parsed.isDDL) {
                    tasks.push(newTask);
                    setMode('ddl');
                } else {
                    tasks.push(newTask);
                }

                input.value = '';
                saveData();
                renderTasks();
            } catch (e) {
                console.error("ADD TASK ERROR:", e);
            }
        }

        // ==== 拖拽功能实现 ====
        function handleDragStart(e, id) {
            if (currentMode !== 'priority') return;
            draggedItemId = id;
            e.dataTransfer.effectAllowed = 'move';
            e.target.style.opacity = '0.4';
        }
        function handleDragOver(e) {
            if (currentMode !== 'priority') return;
            e.preventDefault();
            e.currentTarget.classList.add('drag-over');
        }
        function handleDragLeave(e) {
            e.currentTarget.classList.remove('drag-over');
        }
        function handleDrop(e, targetId) {
            if (currentMode !== 'priority') return;
            e.preventDefault();
            e.currentTarget.classList.remove('drag-over');
            e.currentTarget.style.opacity = '1';
            
            if (draggedItemId === targetId || !draggedItemId) return;

            const fromIdx = tasks.findIndex(t => t.id === draggedItemId);
            const toIdx = tasks.findIndex(t => t.id === targetId);
            
            const [movedItem] = tasks.splice(fromIdx, 1);
            tasks.splice(toIdx, 0, movedItem);
            
            draggedItemId = null;
            saveData();
            renderTasks();
        }
        function handleDragEnd(e) {
            e.target.style.opacity = '1';
            draggedItemId = null;
        }

        function formatDDL(timestamp) {
            const d = new Date(timestamp);
            return `${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:00`;
        }

        function renderTasks() {
            const taskList = document.getElementById('task-list');
            taskList.innerHTML = '';
            
            if (!tasks || tasks.length === 0) {
                taskList.innerHTML = '<li style="color: var(--text-dim); font-size: 0.8rem;">[SYS] QUEUE EMPTY.</li>';
                return;
            }

            let displayTasks = [...tasks];

            if (currentMode === 'ddl') {
                displayTasks.sort((a, b) => {
                    if (a.completed !== b.completed) return a.completed ? 1 : -1;
                    if (a.ddl && b.ddl) return a.ddl - b.ddl;
                    if (a.ddl) return -1;
                    if (b.ddl) return 1;
                    return 0;
                });
            }

            const now = Date.now();

            displayTasks.forEach((task) => {
                const li = document.createElement('li');
                li.className = `task-item ${task.completed ? 'completed' : ''}`;
                
                if (currentMode === 'priority' && !task.completed) {
                    li.classList.add('draggable');
                    li.setAttribute('draggable', 'true');
                    li.ondragstart = (e) => handleDragStart(e, task.id);
                    li.ondragover = handleDragOver;
                    li.ondragleave = handleDragLeave;
                    li.ondrop = (e) => handleDrop(e, task.id);
                    li.ondragend = handleDragEnd;
                }

                let badgeHTML = '';
                if (task.ddl) {
                    const isDanger = !task.completed && task.ddl < now;
                    // 通过 data-time 保存时间戳，让定时器独立判断是否过期
                    badgeHTML = `<div class="ddl-badge ${isDanger ? 'danger' : ''}" data-time="${task.ddl}">${formatDDL(task.ddl)}</div>`;
                }

                const handleHTML = currentMode === 'priority' && !task.completed ? `<span class="drag-handle">≡</span>` : '';

                li.innerHTML = `
                    ${handleHTML}
                    <div class="checkbox"></div>
                    <span class="task-text">${task.text}</span>
                    ${badgeHTML}
                    <button class="delete-btn">×</button>
                `;

                li.querySelector('.checkbox').addEventListener('click', () => toggleTask(task.id));
                li.querySelector('.delete-btn').addEventListener('click', (e) => { e.stopPropagation(); deleteTask(task.id); });

                taskList.appendChild(li);
            });
        }

        function toggleTask(id) {
            const task = tasks.find(t => t.id === id);
            if (!task) return;
            task.completed = !task.completed;
            
            const todayStr = getTodayString();
            if (task.completed) {
                task.completedDate = todayStr;
                if (!logs[todayStr]) logs[todayStr] = [];
                if (!logs[todayStr].find(t => t.id === id)) {
                    logs[todayStr].push({ id: task.id, text: task.text, finish_time: getTimeString() });
                }
            } else {
                const compDate = task.completedDate || todayStr;
                if (logs[compDate]) {
                    logs[compDate] = logs[compDate].filter(t => t.id !== id);
                    if (logs[compDate].length === 0) delete logs[compDate];
                }
                delete task.completedDate;
            }
            saveData();
            renderTasks();
        }

        function deleteTask(id) {
            tasks = tasks.filter(t => t.id !== id);
            saveData();
            renderTasks();
        }

        document.getElementById('add-btn').addEventListener('click', addTask);
        document.getElementById('task-input').addEventListener('keypress', (e) => { if (e.key === 'Enter') addTask(); });

        // 修复3：更安全的初始化机制，防止数据损坏导致的宕机
        async function initApp() {
            try {
                const data = await pywebview.api.load_data();
                // 严格保证 tasks 是个数组，防止意外的 JSON 损坏
                tasks = Array.isArray(data.tasks) ? data.tasks : [];
                logs = data.logs || {};
            } catch(e) {
                tasks = [];
                logs = {};
            }
            document.getElementById('current-date').textContent = getTodayString();
            renderTasks();
        }

        if (window.pywebview) {
            initApp();
        } else {
            window.addEventListener('pywebviewready', initApp);
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    api = Api()
    window = webview.create_window(
        title='PRTS',
        html=html_content,
        width=450,
        height=600,
        frameless=True,      
        easy_drag=True,      
        on_top=True,         
        transparent=True,    
        js_api=api           
    )
    webview.start()