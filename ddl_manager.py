import json
import os
import time
from datetime import datetime

class DDLManager:
    def __init__(self, data_file="prts_archive.json"):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_file = os.path.join(current_dir, data_file)
        self.data = self.load_data()

    def load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if "tasks" not in data: data["tasks"] = []
                    if "logs" not in data: data["logs"] = {}
                    return data
            except Exception as e:
                print(f"Read error: {e}")
        return {"tasks": [], "logs": {}}

    def save_data(self):
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Save error: {e}")

    # 🚀 核心修复：每次操作前，强制从硬盘同步最新数据！
    def sync_from_disk(self):
        self.data = self.load_data()

    def get_all_tasks(self):
        self.sync_from_disk()
        # 🚀 自动重置每日任务
        self._reset_recurring_tasks()
        tasks = self.data["tasks"].copy()
        # 按 ddl 升序排列，None 的排最后
        tasks.sort(key=lambda t: (t.get("ddl") is None, t.get("ddl") or 0))
        return tasks

    def _get_next_reset_time(self):
        """获取明天凌晨 00:00 的时间戳（毫秒）"""
        now = datetime.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
        import datetime as dt
        tomorrow = (now.replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=1))
        return int(tomorrow.timestamp() * 1000)

    def _reset_recurring_tasks(self):
        """检查并重置已到期的每日任务"""
        now = int(time.time() * 1000)
        changed = False
        for task in self.data["tasks"]:
            if task.get("recurring") and task.get("completed") and task.get("nextResetAt"):
                if now >= task["nextResetAt"]:
                    task["completed"] = False
                    task.pop("completedDate", None)
                    task["nextResetAt"] = self._get_next_reset_time()
                    changed = True
        if changed:
            self.save_data()

    def get_sidebar_summary(self):
        self.sync_from_disk()
        now = int(time.time() * 1000)
        danger_count, warning_count, safe_count = 0, 0, 0
        
        for task in self.data["tasks"]:
            if task.get("completed"): continue
            ddl = task.get("ddl")
            if not ddl:
                safe_count += 1
            else:
                hours_left = (ddl - now) / (1000 * 60 * 60)
                if hours_left < 24:
                    danger_count += 1
                elif hours_left < 72:
                    warning_count += 1
                else:
                    safe_count += 1
                    
        return {"danger": danger_count, "warning": warning_count, "safe": safe_count}

    def add_task(self, text, ddl_timestamp=None, priority_index=None, recurring=False):
        self.sync_from_disk() # 防止覆盖大模型的修改
        new_task = {
            "id": int(time.time() * 1000),
            "text": text,
            "completed": False,
            "ddl": ddl_timestamp,
            "recurring": recurring
        }
        if recurring:
            new_task["nextResetAt"] = self._get_next_reset_time()
        if priority_index is not None and 0 <= priority_index <= len(self.data["tasks"]):
            self.data["tasks"].insert(priority_index, new_task)
        else:
            self.data["tasks"].append(new_task)
        self.save_data()
        return new_task

    def delete_task(self, task_id):
        self.sync_from_disk()
        self.data["tasks"] = [t for t in self.data["tasks"] if t.get("id") != task_id]
        self.save_data()

    def toggle_task(self, task_id):
        self.sync_from_disk()
        now_str = datetime.now().strftime("%Y.%m.%d")
        now_time = datetime.now().strftime("%H:%M:%S")
        
        for task in self.data["tasks"]:
            if task.get("id") == task_id:
                task["completed"] = not task["completed"]
                if task["completed"]:
                    task["completedDate"] = now_str
                    if now_str not in self.data["logs"]:
                        self.data["logs"][now_str] = []
                    self.data["logs"][now_str].append({"id": task_id, "text": task["text"], "finish_time": now_time})
                else:
                    comp_date = task.get("completedDate", now_str)
                    if comp_date in self.data["logs"]:
                        self.data["logs"][comp_date] = [t for t in self.data["logs"][comp_date] if t.get("id") != task_id]
                        if not self.data["logs"][comp_date]:
                            del self.data["logs"][comp_date]
                    task.pop("completedDate", None)
                break
        self.save_data()