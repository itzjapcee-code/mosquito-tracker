import streamlit as st
import db_adapter
import pandas as pd

st.set_page_config(page_title="后台管理", page_icon="🔧", layout="wide")

st.title("🔧 系统后台管理")

# 简单密码保护
pwd = st.sidebar.text_input("请输入管理员密码", type="password")
ADMIN_PWD = "admin" 

if pwd != ADMIN_PWD:
    st.info("🔒 请输入密码解锁管理功能。")
    st.stop()

st.success("🔓 管理员身份已验证")

tab_tasks, tab_contribs = st.tabs(["📌 任务管理", "📝 贡献记录清洗"])

# ================= 1. 任务管理 (保持不变) =================
with tab_tasks:
    st.markdown("### 🛠️ 任务列表管理")
    st.caption("您可以删除错误的测试任务，或手动修正任务进度。")
    
    raw_tasks = db_adapter._load_data("tasks")
    
    if not raw_tasks:
        st.info("暂无任务数据。")
    else:
        df_tasks = pd.DataFrame(raw_tasks)
        
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
            num_rows="dynamic"
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
                    # 1. 删除任务
                    db_adapter.delete_item("tasks", task_to_delete['id'])
                    
                    # 2. 级联删除关联的贡献记录
                    all_contribs = db_adapter._load_data("contributions")
                    deleted_count = 0
                    for c in all_contribs:
                        if str(c.get('task_id')) == str(task_to_delete['id']):
                            db_adapter.delete_item("contributions", c['id'])
                            deleted_count += 1
                    
                    st.success(f"任务 {task_to_delete['name']} 已删除！(同时清理了 {deleted_count} 条打卡记录)")
                    st.rerun()
        
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

# ================= 2. 贡献记录清洗 (全新交互) =================
with tab_contribs:
    st.markdown("### 🧹 贡献数据清洗")
    st.caption("直接修改数值或删除错误记录。")
    
    # 获取原始数据以便获取 ID
    raw_contribs = db_adapter._load_data("contributions")
    
    if not raw_contribs:
        st.info("暂无贡献数据。")
    else:
        # 按时间倒序排列
        raw_contribs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # 头部标题
        h1, h2, h3, h4, h5, h6 = st.columns([2, 2, 3, 2, 4, 2])
        h1.markdown("**日期**")
        h2.markdown("**成员**")
        h3.markdown("**任务**")
        h4.markdown("**得分 (可改)**")
        h5.markdown("**描述 (可改)**")
        h6.markdown("**操作**")
        st.divider()

        # 循环渲染每一行 (限制显示最近 50 条以防卡顿)
        for i, item in enumerate(raw_contribs[:50]):
            c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 3, 2, 4, 2])
            
            with c1:
                st.write(item.get('date', ''))
            
            with c2:
                st.write(item.get('user', ''))
            
            with c3:
                st.caption(item.get('task_name', ''))
                
            # 获取当前得分 V
            score_dict = item.get('score', {})
            current_v = score_dict.get('V', 0.0) if isinstance(score_dict, dict) else 0.0
            
            with c4:
                # 修改得分
                new_v = st.number_input(
                    "得分", 
                    value=float(current_v), 
                    key=f"v_{item['id']}", 
                    label_visibility="collapsed",
                    step=0.5
                )
            
            with c5:
                # 修改描述
                new_desc = st.text_input(
                    "描述",
                    value=item.get('description', ''),
                    key=f"desc_{item['id']}",
                    label_visibility="collapsed"
                )
            
            with c6:
                # 操作按钮
                col_save, col_del = st.columns(2)
                with col_save:
                    if st.button("💾", key=f"save_{item['id']}", help="保存修改"):
                        # 更新逻辑
                        # 1. 更新 score.V
                        if isinstance(item.get('score'), dict):
                            item['score']['V'] = new_v
                        else:
                            item['score'] = {'V': new_v}
                        
                        # 2. 更新 description
                        item['description'] = new_desc
                        
                        # 写入数据库 (覆盖整条 item)
                        db_adapter._save_item("contributions", item, item['id'])
                        st.toast(f"✅ 记录已更新！得分: {new_v}")
                        # 不需要 rerun，因为是覆盖写入，下次刷新才变，或者手动 rerun
                        
                with col_del:
                    if st.button("🗑️", key=f"del_{item['id']}", help="删除此记录"):
                        db_adapter.delete_item("contributions", item['id'])
                        st.toast("🗑️ 记录已删除")
                        st.rerun()
            
            st.divider()
