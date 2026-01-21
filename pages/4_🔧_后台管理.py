import streamlit as st
import db_adapter
import pandas as pd

st.set_page_config(page_title="后台管理", page_icon="🔧", layout="wide")

st.title("🔧 系统后台管理")

# 简单密码保护
pwd = st.sidebar.text_input("请输入管理员密码", type="password")
ADMIN_PWD = "admin" # 建议修改复杂一点

if pwd != ADMIN_PWD:
    st.info("🔒 请输入密码解锁管理功能。")
    st.stop()

st.success("🔓 管理员身份已验证")

tab_tasks, tab_contribs = st.tabs(["📌 任务管理", "📝 贡献记录清洗"])

# ================= 1. 任务管理 =================
with tab_tasks:
    st.markdown("### 🛠️ 任务列表管理")
    st.caption("您可以删除错误的测试任务，或手动修正任务进度。")
    
    # 获取原始数据列表（包含隐藏字段如ID）
    raw_tasks = db_adapter._load_data("tasks")
    
    if not raw_tasks:
        st.info("暂无任务数据。")
    else:
        df_tasks = pd.DataFrame(raw_tasks)
        
        # 展示可编辑表格
        # 我们只允许编辑特定列
        edited_df = st.data_editor(
            df_tasks,
            column_config={
                "id": st.column_config.TextColumn("ID", disabled=True),
                "name": "任务名称",
                "progress": st.column_config.NumberColumn("进度%", min_value=0, max_value=100),
                "creator": "负责人",
                "status": st.column_config.SelectboxColumn("状态", options=["进行中", "已完成", "暂停"]),
            },
            use_container_width=True,
            key="task_editor",
            num_rows="dynamic" # 允许增删行? 不，我们只做修改，删除用单独按钮比较安全
        )
        
        st.markdown("---")
        st.subheader("🗑️ 危险操作区")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            task_to_delete = st.selectbox(
                "选择要永久删除的任务", 
                options=raw_tasks, 
                format_func=lambda x: f"{x['name']} (ID: {x['id']})",
                index=None,
                placeholder="请选择..."
            )
            
        with col2:
            if st.button("🚨 确认删除任务", type="primary", disabled=(task_to_delete is None)):
                if task_to_delete:
                    db_adapter.delete_item("tasks", task_to_delete['id'])
                    st.success(f"任务 {task_to_delete['name']} 已删除！")
                    st.rerun()
        
        # 保存编辑更改 (Data Editor 暂时不支持自动回写到 JSON/Firebase，需要手动处理 diff)
        # 这里为了简化，我们提供一个手动更新按钮，或者针对关键字段提供单独的更新入口
        # Streamlit 的 data_editor 返回的是编辑后的 dataframe
        
        # 简单的单条修正逻辑
        st.markdown("#### ✏️ 手动修正进度/状态")
        edit_task = st.selectbox("选择要修正的任务", options=raw_tasks, format_func=lambda x: x['name'], key="edit_sel")
        if edit_task:
            c1, c2, c3 = st.columns(3)
            with c1:
                new_p = st.number_input("新进度", 0, 100, int(edit_task['progress']))
            with c2:
                new_s = st.selectbox("新状态", ["进行中", "已完成", "暂停"], index=["进行中", "已完成", "暂停"].index(edit_task.get('status', '进行中')))
            with c3:
                if st.button("💾 保存修改"):
                    db_adapter.update_item_field("tasks", edit_task['id'], "progress", new_p)
                    db_adapter.update_item_field("tasks", edit_task['id'], "status", new_s)
                    st.success("更新成功！")
                    st.rerun()

# ================= 2. 贡献记录清洗 =================
with tab_contribs:
    st.markdown("### 🧹 贡献数据清洗")
    st.caption("如果成员填错了（比如分值填错、描述写错），可以在这里删除记录。")
    
    df_contribs = db_adapter.get_contributions()
    
    if df_contribs.empty:
        st.info("暂无贡献数据。")
    else:
        # 显示完整表格
        st.dataframe(
            df_contribs.sort_values("timestamp", ascending=False), 
            use_container_width=True
        )
        
        st.markdown("---")
        st.subheader("🗑️ 删除记录")
        
        # 构造一个易读的选项列表
        # 需要确保 df_contribs 有 id 列。get_contributions 可能在 json_normalize 时丢失了 id 如果它在 root level
        # 我们重新加载 raw data 来获取 ID
        raw_contribs = db_adapter._load_data("contributions")
        
        if not raw_contribs:
            st.warning("数据读取异常")
        else:
            # 按时间倒序
            raw_contribs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            record_to_del = st.selectbox(
                "选择要删除的记录",
                options=raw_contribs,
                format_func=lambda x: f"[{x.get('date')}] {x.get('user')} - {x.get('task_name')} (ID: {x.get('id')[-4:]})",
                placeholder="请选择一条记录..."
            )
            
            if st.button("🚨 确认删除该条记录", type="primary", disabled=(record_to_del is None)):
                if record_to_del:
                    # 尝试删除
                    if "id" not in record_to_del:
                        st.error("该记录缺少 ID，无法删除（可能是旧数据）。建议手动清理 JSON 文件。")
                    else:
                        db_adapter.delete_item("contributions", record_to_del['id'])
                        st.success("记录已删除！")
                        st.rerun()
