import streamlit as st
import db_adapter
import pandas as pd

st.set_page_config(
    page_title="项目全景",
    page_icon="🌳",
    layout="wide"
)

# ================= 系统状态监测 =================
with st.sidebar:
    st.markdown("### 🛡️ 系统状态")
    db_info = db_adapter.get_db()
    if db_info["type"] == "firebase":
        st.success("🟢 **云端数据库已连接**\n\n支持多人并发，数据永久存储。")
    else:
        st.error("🔴 **本地临时模式 (高危)**\n\n未配置 Firebase！\n数据将在重启后丢失。\n**严禁多人同时操作！**")
        st.info("👉 请参照教程配置 Secrets")

st.title("🌳 蚊虫识别系统 · 作战地图")
st.markdown("### 🎯 一眼看懂项目进度与瓶颈")

# 获取所有进行中的任务
active_tasks = db_adapter.get_all_active_tasks()

st.markdown("---")

# ================= 纯 Streamlit 组件构建树状视图 =================
# 根节点
st.info("🦟 **蚊虫识别系统 (ROOT)**")

# 遍历一级分类
for category, subcategories in db_adapter.CATEGORIES.items():
    # 使用 Expander 模拟一级分支，默认全部展开以便“一眼看全”
    with st.expander(f"📂 {category}", expanded=True):
        
        # 遍历二级分类
        for sub in subcategories:
            # 筛选该分支下的任务
            related_tasks = [t for t in active_tasks if t['category'] == category and t['subcategory'] == sub]
            
            # 二级分支标题 + 任务统计
            task_count = len(related_tasks)
            st.markdown(f"**└─ 📁 {sub}** <small style='color:gray'>({task_count} 个任务)</small>", unsafe_allow_html=True)
            
            if not related_tasks:
                st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;*(暂无任务)*")
            else:
                # 遍历任务 (叶子节点)
                for task in related_tasks:
                    p = task['progress']
                    name = task['name']
                    creator = task.get('creator', '?')
                    
                    # 状态图标与颜色
                    icon = "🔴"
                    color_style = "border-left: 5px solid #FF5252;" # 红条
                    bg_color = "#FFEBEE"
                    if p >= 30: 
                        icon = "🟡"
                        color_style = "border-left: 5px solid #FFD740;" # 黄条
                        bg_color = "#FFFDE7"
                    if p >= 80: 
                        icon = "🟢"
                        color_style = "border-left: 5px solid #66BB6A;" # 绿条
                        bg_color = "#E8F5E9"
                    
                    # 使用 HTML 卡片模拟叶子节点
                    st.markdown(
                        f"""
                        <div style="
                            margin-left: 40px;
                            margin-bottom: 8px;
                            padding: 8px 12px;
                            background-color: {bg_color};
                            border-radius: 4px;
                            {color_style}
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                        ">
                            <div style="flex: 2;">
                                <strong>{icon} {name}</strong>
                                <div style="font-size: 0.8em; color: #666;">
                                    👤 {creator}
                                </div>
                            </div>
                            <div style="flex: 1; text-align: right;">
                                <div style="font-weight: bold; font-size: 1.1em;">{p}%</div>
                                <div style="font-size: 0.7em; color: #666;">PROGRESS</div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
            
            # 分隔线
            st.markdown("<div style='height: 10px'></div>", unsafe_allow_html=True)

st.markdown("---")

# ================= 关键问题看板 =================
st.subheader("🚨 风险预警 (Focus Areas)")
risk_tasks = [t for t in active_tasks if t['progress'] < 30]

if not risk_tasks:
    st.success("🎉 目前没有严重滞后的任务！")
else:
    cols = st.columns(3)
    for i, task in enumerate(risk_tasks):
        with cols[i % 3]:
            st.error(f"**{task['name']}**")
            st.caption(f"📍 {task['category']} > {task['subcategory']}")
            st.progress(task['progress'] / 100)
            st.caption(f"负责人: {task.get('creator', '未分配')}")

st.markdown("---")
st.markdown("#### 🏆 最新动态")
df = db_adapter.get_contributions()
if not df.empty:
    # 动态确定要显示的列，防止KeyError
    cols = ["date", "user", "task_name", "description"]
    # 兼容新旧数据结构 V 或 score.V
    if "V" in df.columns: cols.insert(3, "V")
    elif "score.V" in df.columns: cols.insert(3, "score.V")
    
    # 过滤出存在的列
    final_cols = [c for c in cols if c in df.columns]
    
    st.dataframe(
        df[final_cols].sort_values("date", ascending=False).head(5), 
        use_container_width=True
    )
