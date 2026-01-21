import streamlit as st
import db_adapter
import pandas as pd

st.set_page_config(
    page_title="项目全景",
    page_icon="🌳",
    layout="wide"
)

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
                    status = task.get('status', '进行中')
                    
                    # 默认样式 (进行中)
                    icon = "🔴"
                    color_style = "border-left: 5px solid #FF5252;" # 红条
                    bg_color = "#FFEBEE"
                    status_text = f"{p}%"
                    
                    if status == "已完成":
                        icon = "✅"
                        color_style = "border-left: 5px solid #4CAF50;" # 深绿条
                        bg_color = "#E8F5E9"
                        status_text = "DONE"
                    elif status == "暂停":
                        icon = "⏸️"
                        color_style = "border-left: 5px solid #9E9E9E;" # 灰条
                        bg_color = "#F5F5F5"
                        status_text = "PAUSED"
                    else:
                        # 进行中状态根据进度变色
                        if p >= 30: 
                            icon = "🟡"
                            color_style = "border-left: 5px solid #FFD740;" 
                            bg_color = "#FFFDE7"
                        if p >= 80: 
                            icon = "🟢"
                            color_style = "border-left: 5px solid #66BB6A;" 
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
                                <div style="font-weight: bold; font-size: 1.1em;">{status_text}</div>
                                <div style="font-size: 0.7em; color: #666;">{status}</div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
            
            # 分隔线
            st.markdown("<div style='height: 10px'></div>", unsafe_allow_html=True)

# ================= 兜底展示：未分类/匹配失败的任务 =================
# 收集所有已显示的任务 ID
shown_task_ids = set()
for category, subcategories in db_adapter.CATEGORIES.items():
    for sub in subcategories:
        related = [t for t in active_tasks if t['category'] == category and t['subcategory'] == sub]
        for t in related:
            shown_task_ids.add(t['id'])

# 找出漏网之鱼
orphan_tasks = [t for t in active_tasks if t.get('id') not in shown_task_ids]

if orphan_tasks:
    with st.expander("📂 其他/未分类任务 (Orphan Tasks)", expanded=True):
        st.warning(f"发现 {len(orphan_tasks)} 个任务未匹配到现有分类结构，请检查分类名称是否一致。")
        for task in orphan_tasks:
            st.markdown(f"**{task['name']}** (Category: `{task.get('category')}` / `{task.get('subcategory')}`)")

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
