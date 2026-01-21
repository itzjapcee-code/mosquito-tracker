import json
import os
import uuid
from datetime import datetime
import pandas as pd
import streamlit as st

# 尝试导入 firebase 相关库
try:
    import firebase_admin
    from firebase_admin import credentials
    from firebase_admin import firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

# ================= 数据库连接管理 =================
_db_client = None

def get_db():
    """
    获取数据库客户端。
    优先尝试连接 Firebase (Streamlit Secrets)。
    如果未配置，降级为本地 JSON 模式。
    """
    global _db_client
    
    # 1. 检查是否已初始化
    if _db_client:
        return _db_client

    # 2. 尝试连接 Firebase
    # 检查 secrets 是否包含 firebase 配置
    if FIREBASE_AVAILABLE and "firebase" in st.secrets:
        try:
            # 防止重复初始化 app
            if not firebase_admin._apps:
                # 从 st.secrets 构建证书字典
                key_dict = dict(st.secrets["firebase"])
                cred = credentials.Certificate(key_dict)
                firebase_admin.initialize_app(cred)
            
            _db_client = {
                "type": "firebase",
                "client": firestore.client()
            }
            return _db_client
        except Exception as e:
            print(f"Firebase 连接失败，回退到本地模式: {e}")
    
    # 3. 回退到本地 JSON 模式
    _db_client = {
        "type": "local",
        "task_file": "tasks_db.json",
        "contrib_file": "contributions_db.json"
    }
    return _db_client

# ================= 基础 I/O (多态适配) =================

def _load_data(collection_name):
    db = get_db()
    if db["type"] == "firebase":
        # Firebase 模式
        docs = db["client"].collection(collection_name).stream()
        return [doc.to_dict() for doc in docs]
    else:
        # 本地 JSON 模式
        filename = db["task_file"] if collection_name == "tasks" else db["contrib_file"]
        if not os.path.exists(filename):
            return []
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

def _save_item(collection_name, item, item_id=None):
    db = get_db()
    if db["type"] == "firebase":
        # Firebase 模式
        # 如果没有指定 ID，让 Firebase 自动生成或使用 item 中的 id
        if not item_id and "id" in item:
            item_id = item["id"]
        
        if item_id:
            db["client"].collection(collection_name).document(str(item_id)).set(item)
        else:
            db["client"].collection(collection_name).add(item)
    else:
        # 本地 JSON 模式
        data = _load_data(collection_name)
        # 如果是更新操作（检查 ID）
        if "id" in item:
            existing_idx = next((i for i, x in enumerate(data) if x.get("id") == item["id"]), -1)
            if existing_idx >= 0:
                data[existing_idx] = item
            else:
                data.append(item)
        else:
            data.append(item)
        
        filename = db["task_file"] if collection_name == "tasks" else db["contrib_file"]
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# ================= 任务分支管理 =================
def create_task(creator, name, category, subcategory, difficulty_level="B 级 (常规)", operator=None):
    # 初始参与者
    contributors = [creator]
    if operator and operator != creator and operator not in contributors:
        contributors.append(operator)

    new_task = {
        "id": str(uuid.uuid4())[:8],
        "creator": creator,
        "contributors": contributors,
        "name": name,
        "category": category,
        "subcategory": subcategory,
        "difficulty": difficulty_level,
        "progress": 0,
        "status": "进行中",
        "created_at": datetime.now().strftime("%Y-%m-%d"),
        "updated_at": datetime.now().strftime("%Y-%m-%d")
    }
    
    _save_item("tasks", new_task, new_task["id"])
    return new_task

def get_all_active_tasks():
    tasks = _load_data("tasks")
    return [t for t in tasks if t.get("status") == "进行中"]

def get_user_involved_tasks(user):
    tasks = _load_data("tasks")
    return [t for t in tasks if t.get("status") == "进行中" and user in t.get("contributors", [])]

def join_task(user, task_id):
    tasks = _load_data("tasks")
    target_task = next((t for t in tasks if t["id"] == task_id), None)
    
    if target_task:
        contributors = target_task.get("contributors", [])
        if user not in contributors:
            contributors.append(user)
            target_task["contributors"] = contributors
            _save_item("tasks", target_task, task_id)
            return True
    return False

def update_task_progress(task_id, new_progress):
    tasks = _load_data("tasks")
    target_task = next((t for t in tasks if t["id"] == task_id), None)
    
    if target_task:
        target_task["progress"] = new_progress
        target_task["updated_at"] = datetime.now().strftime("%Y-%m-%d")
        if new_progress >= 100:
            target_task["status"] = "已完成"
        _save_item("tasks", target_task, task_id)

# ================= 每日贡献管理 =================
def add_contribution(user, task_id, task_name, category, subcategory, score_data, description, date=None):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    entry = {
        # 贡献记录不需要唯一ID，用 uuid 生成一个防止冲突
        "id": str(uuid.uuid4()), 
        "date": date,
        "user": user,
        "task_id": task_id,
        "task_name": task_name,
        "category": category,
        "subcategory": subcategory,
        "score": score_data,
        "description": description,
        "timestamp": datetime.now().isoformat()
    }
    
    _save_item("contributions", entry, entry["id"])
    return True

def get_contributions():
    data = _load_data("contributions")
    if not data:
        return pd.DataFrame(columns=["date", "user", "category", "score", "description"])
    
    df = pd.DataFrame(data)
    # 展平 score 字段
    if not df.empty and 'score' in df.columns:
        # 处理可能为空的 score
        def normalize_score(s):
            if isinstance(s, dict): return s
            return {}
        
        score_df = pd.json_normalize(df['score'].apply(normalize_score))
        df = pd.concat([df.drop('score', axis=1), score_df], axis=1)
    
    return df

# ================= 数据删除/修正接口 =================
def delete_item(collection_name, item_id):
    """通用删除接口"""
    db = get_db()
    if db["type"] == "firebase":
        # Firebase 删除
        db["client"].collection(collection_name).document(str(item_id)).delete()
        return True
    else:
        # 本地 JSON 删除
        data = _load_data(collection_name)
        # 过滤掉要删除的 ID
        new_data = [d for d in data if str(d.get("id")) != str(item_id)]
        
        # 如果长度没变，说明没找到
        if len(new_data) == len(data):
            return False
            
        filename = db["task_file"] if collection_name == "tasks" else db["contrib_file"]
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        return True

def update_item_field(collection_name, item_id, field, value):
    """通用字段更新接口"""
    db = get_db()
    if db["type"] == "firebase":
        db["client"].collection(collection_name).document(str(item_id)).update({field: value})
    else:
        data = _load_data(collection_name)
        found = False
        for d in data:
            if str(d.get("id")) == str(item_id):
                d[field] = value
                found = True
                break
        
        if found:
            filename = db["task_file"] if collection_name == "tasks" else db["contrib_file"]
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

# ================= 配置 =================
CATEGORIES = {
    "产品研发": ["收音数据样本采集", "模型训练", "硬件设计", "优化迭代"],
    "项目申报": ["材料撰写", "答辩/汇报"],
    "商业落地": ["客户对接", "现场部署"]
}

SCORE_CONFIG = {
    "B_Base": {
        "🌟 完成关键节点 (Milestone)": 100.0,
        "🔨 有效推进 (Progress)": 50.0,
        "🔧 日常维护/修复 (Fix)": 20.0,
        "📝 文档/会议 (Support)": 10.0
    },
    "D_Difficulty": {
        "S 级 (极难/攻坚)": 1.5,
        "A 级 (困难)": 1.2,
        "B 级 (常规)": 1.0,
        "C 级 (杂活)": 0.8
    },
    "M_Musk": {
        "Level 3 (颠覆 - 删除/重构)": 2.0,
        "Level 2 (加速 - 简化/加速)": 1.5,
        "Level 1 (常规 - 自动化/执行)": 1.0,
        "Level 0 (反向 - 愚蠢的勤奋)": 0.1
    }
}
