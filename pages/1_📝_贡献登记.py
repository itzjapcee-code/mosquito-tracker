import streamlit as st
import db_adapter
from datetime import datetime

st.set_page_config(page_title="贡献登记", page_icon="📝")

st.title("📝 每日贡献登记 (Task Based)")
st.markdown("基于 **工作分支 (Task Branch)** 进行每日进度更新与量化。")

# 1. 确认身份
st.sidebar.header("👤 身份确认")
user_name = st.sidebar.text_input("请输入您的姓名", key="current_user_name")

if not user_name:
    st.info("👈 请先在左侧侧边栏输入您的姓名，加载您的任务列表。")
    st.stop()

# 2. 任务管理 (Tabs)
tab_my, tab_market, tab_new = st.tabs(["📌 我的任务", "🌍 任务广场 (加入别人)", "➕ 新建任务分支"])

selected_task = None

# === Tab 1: 我的任务 (参与的) ===
with tab_my:
    my_tasks = db_adapter.get_user_involved_tasks(user_name)
    if not my_tasks:
        st.warning("您当前没有参与任何任务分支。您可以去“任务广场”加入，或“新建任务分支”。")
    else:
        # 格式化任务显示名称
        task_options = {f"[{t['category']}-{t['subcategory']}] {t['name']} (当前进度: {t['progress']}%)": t for t in my_tasks}
        selected_task_label = st.selectbox("选择今天要更新的任务", list(task_options.keys()))
        if selected_task_label:
            selected_task = task_options[selected_task_label]
            # 显示该任务的贡献者
            creator = selected_task.get("creator", "未知")
            contributors = selected_task.get("contributors", [])
            st.info(f"👑 **负责人**: {creator}  |  🤝 **参与者**: {', '.join(contributors)}")
            st.success(f"已选中任务：**{selected_task['name']}**")

# === Tab 2: 任务广场 (所有进行中的) ===
with tab_market:
    st.markdown("#### 🌍 发现团队正在进行的所有分支")
    all_tasks = db_adapter.get_all_active_tasks()
    
    # 排除我已经参与的
    my_task_ids = [t["id"] for t in db_adapter.get_user_involved_tasks(user_name)]
    available_tasks = [t for t in all_tasks if t["id"] not in my_task_ids]
    
    if not available_tasks:
        st.info("暂时没有您可以加入的新任务（所有任务您都已参与，或暂无任务）。")
    else:
        for t in available_tasks:
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown(f"**{t['name']}**")
                st.caption(f"{t['category']} / {t['subcategory']}")
            with col2:
                st.progress(t['progress'] / 100)
                st.caption(f"进度: {t['progress']}% | 负责人: {t.get('creator', '未知')}")
            with col3:
                if st.button("➕ 加入", key=f"join_{t['id']}"):
                    db_adapter.join_task(user_name, t['id'])
                    st.success(f"已加入任务 {t['name']}！")
                    st.rerun()
            st.markdown("---")

# === Tab 3: 新建任务 ===
with tab_new:
    st.markdown("#### 创建一个新的长期工作分支")
    st.caption("提示：创建后请切换回“我的任务”标签页进行打卡。")
    
    new_task_name = st.text_input("任务名称", placeholder="例如：优化CNN模型结构")
    
    # 增加负责人指定逻辑
    assignee = st.text_input("指定负责人 (默认为您)", value=user_name, help="如果您是为别人创建任务，请在此修改名字")
    
    c1, c2 = st.columns(2)
    with c1:
        cat_opts = list(db_adapter.CATEGORIES.keys())
        new_cat = st.selectbox("一级分类", cat_opts, key="new_task_cat")
    with c2:
        sub_opts = db_adapter.CATEGORIES[new_cat]
        new_sub = st.selectbox("二级分类", sub_opts, key="new_task_sub")

    diff_opts = list(db_adapter.SCORE_CONFIG["D_Difficulty"].keys())
    new_diff = st.selectbox("预估任务难度", diff_opts, index=2)

    if st.button("✨ 创建并选中该任务", type="primary"):
        if not new_task_name:
            st.error("请输入任务名称")
        elif not assignee:
            st.error("必须指定一个负责人")
        else:
            # 这里的 assignee 就是用户输入的“负责人”
            # user_name 是当前操作人，自动加入参与者
            new_t = db_adapter.create_task(assignee, new_task_name, new_cat, new_sub, new_diff, operator=user_name)
            st.success(f"任务分支“{new_task_name}”创建成功！负责人：{assignee}")
            st.rerun()

st.markdown("---")

# 3. 每日打卡区域
if selected_task:
    st.subheader(f"🚀 更新进度: {selected_task['name']}")
    
    # 进度更新
    st.markdown("#### 📈 进度更新")
    current_p = selected_task['progress']
    new_progress = st.slider("更新当前总进度 (%)", 0, 100, int(current_p))
    if new_progress == 100:
        st.caption("🎉 恭喜！任务将标记为已完成。")

    st.markdown("#### 🧮 今日量化评分 (The Math Model)")
    default_d_index = list(db_adapter.SCORE_CONFIG["D_Difficulty"].keys()).index(selected_task['difficulty'])
    
    col_b, col_d, col_m = st.columns(3)
    with col_b:
        st.markdown("**B (Base) 今日产出类型**")
        b_opts = list(db_adapter.SCORE_CONFIG["B_Base"].keys())
        b_sel = st.selectbox("工作性质", b_opts)
        b_val = db_adapter.SCORE_CONFIG["B_Base"][b_sel]
    
    with col_d:
        st.markdown("**D (Difficulty) 任务难度**")
        d_opts = list(db_adapter.SCORE_CONFIG["D_Difficulty"].keys())
        d_sel = st.selectbox("难度系数", d_opts, index=default_d_index)
        d_val = db_adapter.SCORE_CONFIG["D_Difficulty"][d_sel]

    with col_m:
        st.markdown("**M (Musk) 马斯克加速度**")
        m_opts = list(db_adapter.SCORE_CONFIG["M_Musk"].keys())
        m_sel = st.selectbox("核心灵魂", m_opts, index=2)
        m_val = db_adapter.SCORE_CONFIG["M_Musk"][m_sel]

    # 实时计算 V (因为都在 form 外面，所以会实时更新)
    v_score = round((b_val * d_val) * m_val, 2)
    
    # 显式展示计算过程，方便核对
    st.info(
        f"""
        ⚡ **今日得分 (V): {v_score}**
        
        🧮 计算公式: **{b_val}** (基础分) × **{d_val}** (难度) × **{m_val}** (加速度)
        """
    )

    with st.form("daily_update_form"):
        date = st.date_input("日期", datetime.now())
        description = st.text_area("今日工作内容描述", placeholder="例如：完成了数据清洗脚本编写...")
        submit_update = st.form_submit_button("✅ 提交今日登记")

        if submit_update:
            if not description:
                st.error("请填写描述！")
            else:
                db_adapter.update_task_progress(selected_task['id'], new_progress)
                
                score_data = {
                    "V": v_score,
                    "B_val": b_val, "B_label": b_sel,
                    "D_val": d_val, "D_label": d_sel,
                    "M_val": m_val, "M_label": m_sel
                }
                
                db_adapter.add_contribution(
                    user_name, 
                    selected_task['id'], 
                    selected_task['name'],
                    selected_task['category'], 
                    selected_task['subcategory'],
                    score_data, 
                    description, 
                    date.strftime("%Y-%m-%d")
                )
                
                st.success("✅ 登记成功！进度已更新。")
                st.balloons()
                import time
                time.sleep(1)
                st.rerun()

else:
    st.info("👋 请先在上方的【我的任务】标签页中选择一个任务，或者新建/加入一个任务。")
