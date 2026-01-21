import streamlit as st
import db_adapter
import pandas as pd
import altair as alt

st.set_page_config(page_title="数据看板", page_icon="📊", layout="wide")

st.title("📊 团队贡献看板 (Task & Score)")

df = db_adapter.get_contributions()

if df.empty:
    st.warning("暂无数据，请先去【贡献登记】页面添加数据。")
else:
    # --- 0. 数据清洗与列名对齐 ---
    # 确保 'score.V' 和 'V' 都能识别 (兼容新旧数据结构)
    if 'V' in df.columns and 'score.V' not in df.columns:
        df['score.V'] = df['V']
    elif 'score.V' in df.columns and 'V' not in df.columns:
        df['V'] = df['score.V']
    
    # 侧边栏筛选
    with st.sidebar:
        st.header("🔍 筛选")
        if 'user' in df.columns:
            selected_users = st.multiselect("选择成员", df['user'].unique(), default=df['user'].unique())
            
            df['date'] = pd.to_datetime(df['date'])
            min_date = df['date'].min().date()
            max_date = df['date'].max().date()
            date_range = st.date_input("日期范围", [min_date, max_date])

            mask = df['user'].isin(selected_users)
            if len(date_range) == 2:
                mask = mask & (df['date'].dt.date >= date_range[0]) & (df['date'].dt.date <= date_range[1])
            
            filtered_df = df[mask]
        else:
            filtered_df = df

    # 1. 核心指标卡片
    col1, col2, col3, col4 = st.columns(4)
    
    total_v = filtered_df['V'].sum() if 'V' in filtered_df.columns else 0
    
    col1.metric("累计贡献总分 (Sum V)", f"{total_v:.0f}")
    col2.metric("累计贡献条目", len(filtered_df))
    col3.metric("活跃成员数", filtered_df['user'].nunique() if 'user' in filtered_df.columns else 0)
    
    top_category = filtered_df['category'].mode()[0] if not filtered_df.empty else "N/A"
    col4.metric("最热门场景", top_category)

    # 2. 成员积分榜 (表格)
    st.markdown("### 🏆 成员积分风云榜")
    
    # 只要有 user 列就显示表格，哪怕没有分值
    if 'user' in filtered_df.columns:
        # 准备聚合数据
        if 'V' in filtered_df.columns:
            agg_dict = {'V': 'sum', 'task_name': 'count', 'date': 'max'}
            sort_by = 'V'
        else:
            agg_dict = {'task_name': 'count', 'date': 'max'}
            sort_by = 'task_name'
            
        leaderboard = filtered_df.groupby('user').agg(agg_dict).reset_index()
        
        # 补全列名逻辑
        leaderboard.columns = ['成员', '总积分 (V)', '贡献次数', '最近活跃时间'] if 'V' in filtered_df.columns else ['成员', '贡献次数', '最近活跃时间']
        
        # 排序
        sort_col = '总积分 (V)' if 'V' in filtered_df.columns else '贡献次数'
        leaderboard = leaderboard.sort_values(sort_col, ascending=False).reset_index(drop=True)
        
        # 增加排名列
        leaderboard.insert(0, '排名', leaderboard.index + 1)
        
        # 格式化
        if '总积分 (V)' in leaderboard.columns:
            leaderboard['总积分 (V)'] = leaderboard['总积分 (V)'].map(lambda x: f"{x:.1f}")
            
            st.dataframe(
                leaderboard,
                use_container_width=True,
                column_config={
                    "排名": st.column_config.NumberColumn(format="🥇 %d"),
                    "总积分 (V)": st.column_config.ProgressColumn(
                        "总积分",
                        format="%s",
                        min_value=0,
                        max_value=float(leaderboard['总积分 (V)'].max()) if not leaderboard.empty else 100,
                    ),
                },
                hide_index=True
            )
        else:
            st.dataframe(leaderboard, use_container_width=True)
    else:
        st.info("暂无足够的评分数据生成排行榜。")

    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("📈 成员贡献趋势")
        if 'V' in filtered_df.columns:
            trend = filtered_df.groupby(['date', 'user'])['V'].sum().reset_index()
            # 使用 Altair 绘制更好看的折线图
            chart = alt.Chart(trend).mark_line(point=True).encode(
                x=alt.X('date', title='日期'),
                y=alt.Y('V', title='单日积分'),
                color='user',
                tooltip=['date', 'user', 'V']
            ).interactive()
            st.altair_chart(chart, use_container_width=True)

    with col_chart2:
        st.subheader("🍩 各场景投入分布")
        if 'category' in filtered_df.columns:
            cat_counts = filtered_df['category'].value_counts().reset_index()
            cat_counts.columns = ['category', 'count']
            
            # 使用 Altair 绘制环形图 (Donut Chart)
            base = alt.Chart(cat_counts).encode(
                theta=alt.Theta("count", stack=True),
                color=alt.Color("category", legend=alt.Legend(title="场景分类"))
            )
            
            pie = base.mark_arc(outerRadius=120, innerRadius=80).encode(
                order=alt.Order("count", sort="descending"),
                tooltip=["category", "count"]
            )
            
            text = base.mark_text(radius=140).encode(
                text="count",
                order=alt.Order("count", sort="descending"),
                color=alt.value("black")  
            )
            
            st.altair_chart(pie + text, use_container_width=True)

    # 4. 详细数据表
    st.subheader("📋 详细记录")
    
    # 动态适配列名 V 或 score.V
    v_col = 'V' if 'V' in filtered_df.columns else 'score.V'
    
    cols_to_show = ["date", "user", "task_name", "category", "subcategory", v_col, "description"]
    cols_to_show = [c for c in cols_to_show if c in filtered_df.columns]
    
    if not filtered_df.empty:
        rename_map = {
            "task_name": "任务分支",
            v_col: "得分 (V)",
            "description": "今日产出",
            "user": "成员",
            "category": "场景"
        }
        st.dataframe(
            filtered_df[cols_to_show].sort_values("date", ascending=False).rename(columns=rename_map), 
            use_container_width=True
        )
