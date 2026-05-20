"""
Device identity module for PRTS Bridge
"""
import os
import uuid
import hashlib

# 固定设备ID存储文件
DEVICE_FILE = os.path.join(os.path.dirname(__file__), ".device_id")

def get_device_id() -> str:
    """获取或生成固定的设备ID"""
    if os.path.exists(DEVICE_FILE):
        with open(DEVICE_FILE, "r") as f:
            return f.read().strip()
    
    # 生成新的设备ID
    # 基于机器特征生成
    device_id = str(uuid.uuid4())
    
    with open(DEVICE_FILE, "w") as f:
        f.write(device_id)
    
    return device_id

def generate_signature(data: str, _: int, _2: str) -> str:
    """生成认证签名"""
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()
