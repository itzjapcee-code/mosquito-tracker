import streamlit as st
import torch
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

# 将父目录加入 path 以便导入 model_utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model_utils import (
    load_model_from_bytes, 
    run_infer, 
    SR, 
    N_MFCC
)

import json

st.set_page_config(page_title="蚊子识别模型评估看板", page_icon="🦟", layout="wide")

if "history" not in st.session_state:
    st.session_state["history"] = []
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0

st.title("🦟 智能蚊音识别系统 - 性能评估看板")
st.markdown("---")
st.info("💡 **使用说明**: 上传 .pth 模型文件（可选配套 .json 配置文件）和测试音频。")

with st.sidebar:
    st.header("⚙️ 控制面板")

    work_mode = st.radio(
        "模式",
        ["单模型评估", "模型对比（CNN vs CNN-LSTM）"],
        key="work_mode_radio"
    )

    st.subheader("1️⃣ 上传测试音频 (.wav)")
    col_u1, col_u2 = st.columns([3, 1])
    with col_u2:
        if st.button("🗑️", help="清空当前测试集", key="btn_clear_audio"):
            st.session_state["uploader_key"] += 1
            st.rerun()

    audio_files = st.file_uploader(
        "选择一批测试音频",
        type=["wav"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state['uploader_key']}"
    )

    st.markdown("---")

    if work_mode == "单模型评估":
        st.subheader("2️⃣ 上传模型")
        arch = st.selectbox("选择模型结构", ["CNN", "CNN-LSTM"], key="single_arch")
        model_file = st.file_uploader("模型权重 (.pth)", type=["pth"], key="single_model_uploader")
        config_file = st.file_uploader("模型配置 (.json, 可选)", type=["json"], key="single_config_uploader")
    else:
        st.subheader("2️⃣ 上传对比模型")
        
        # --- 模型 A 配置 ---
        st.caption("🅰️ 模型 A (基准)")
        arch_a = st.selectbox("模型 A 结构", ["CNN", "CNN-LSTM"], index=0, key="arch_a")
        model_file_a = st.file_uploader(f"模型 A 权重 (.pth)", type=["pth"], key="cmp_model_a")
        config_file_a = st.file_uploader(f"模型 A 配置 (.json)", type=["json"], key="cmp_config_a")
        
        st.markdown("---")
        
        # --- 模型 B 配置 ---
        st.caption("🅱️ 模型 B (对照)")
        arch_b = st.selectbox("模型 B 结构", ["CNN", "CNN-LSTM"], index=1, key="arch_b")
        model_file_b = st.file_uploader(f"模型 B 权重 (.pth)", type=["pth"], key="cmp_model_b")
        config_file_b = st.file_uploader(f"模型 B 配置 (.json)", type=["json"], key="cmp_config_b")

# 辅助函数：解析配置
def parse_config(json_file):
    if json_file is None:
        return {}
    try:
        return json.load(json_file)
    except Exception as e:
        return {"error": str(e)}

# 固定根容器（避免 DOM removeChild）
root = st.empty()

with root.container():
    if not audio_files:
        st.info("👈 请先在左侧上传一批测试音频（.wav）。")
    else:
        if work_mode == "单模型评估":
            if not model_file:
                st.warning("👈 尚未上传模型文件。请在左侧上传 .pth 文件。")
            else:
                try:
                    # 显示配置信息
                    if config_file:
                        cfg = parse_config(config_file)
                        with st.expander("📄 模型训练参数 (Metadata)", expanded=True):
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("N_MELS", cfg.get("N_MELS", "N/A"))
                            c2.metric("HOP_LENGTH", cfg.get("HOP_LENGTH", "N/A"))
                            c3.metric("BATCH_SIZE", cfg.get("BATCH_SIZE", "N/A"))
                            c4.metric("训练时间", cfg.get("saved_at", "N/A"))

                    model, msg = load_model_from_bytes(model_file, arch)
                    if model is None:
                        st.error(msg)
                    else:
                        st.success(msg)
                        
                        with st.spinner("正在进行推理分析..."):
                            df, metrics = run_infer(model, audio_files)

                        c1, c2, c3, c4, c5 = st.columns(5)
                        c1.metric("测试样本总数", metrics["samples"])
                        c2.metric("检出蚊子数", metrics["mosquito"], delta_color="inverse")
                        c3.metric("准确率（基于文件名）", metrics["acc_str"])
                        c4.metric("读取失败数", metrics["read_fail"])
                        with c5:
                            if st.button("💾 记录本次结果", key="btn_save_single", type="primary"):
                                st.session_state["history"].insert(0, {
                                    "时间": datetime.now().strftime("%H:%M:%S"),
                                    "模式": "单模型",
                                    "结构": arch,
                                    "模型名称": model_file.name,
                                    "样本数": metrics["samples"],
                                    "蚊子数": metrics["mosquito"],
                                    "准确率": metrics["acc_str"],
                                    "读取失败": metrics["read_fail"],
                                })
                                st.success("已保存！")

                        st.subheader("🧮 混淆矩阵")
                        if metrics["cm"] is None:
                            st.write("没有可用于计算混淆矩阵的标签（文件名不含 pos/mosquito 或 neg/other/noise），或全部读取失败。")
                        else:
                            st.dataframe(metrics["cm"], use_container_width=True)

                        st.subheader("📄 详细检测报告")
                        show_df = df.copy()
                        show_df["置信度"] = (show_df["置信度"] * 100).map(lambda x: f"{x:.1f}%")
                        st.dataframe(
                            show_df[["文件名", "真实标签", "预测标签", "置信度", "判定"]],
                            use_container_width=True,
                            hide_index=True
                        )

                        st.subheader("▶️ 单条音频播放")
                        name_list = [f.name for f in audio_files]
                        sel = st.selectbox("选择一个文件播放", name_list, key="sel_play_single")
                        sel_file = next((f for f in audio_files if f.name == sel), None)
                        if sel_file is not None:
                            st.audio(sel_file, format="audio/wav")
                except Exception as e:
                     st.error(f"发生运行时错误: {e}")
                     st.exception(e)

        else:
            if not (model_file_a and model_file_b):
                st.warning("👈 请在左侧上传两个模型文件（.pth）开始对比。")
            else:
                try:
                    model_a, msg_a = load_model_from_bytes(model_file_a, arch_a)
                    model_b, msg_b = load_model_from_bytes(model_file_b, arch_b)

                    if model_a is None:
                        st.error(f"模型 A 加载失败: {msg_a}")
                    if model_b is None:
                        st.error(f"模型 B 加载失败: {msg_b}")

                    if (model_a is not None) and (model_b is not None):
                        st.success(f"模型 A ({arch_a}): {msg_a}")
                        st.success(f"模型 B ({arch_b}): {msg_b}")
                        
                        # --- 新增：参数对比表 ---
                        if config_file_a or config_file_b:
                            cfg1 = parse_config(config_file_a)
                            cfg2 = parse_config(config_file_b)
                            
                            st.subheader("📋 训练参数对比")
                            all_keys = sorted(list(set(cfg1.keys()) | set(cfg2.keys())))
                            filter_keys = ["saved_at"]
                            disp_keys = [k for k in all_keys if k not in filter_keys]
                            
                            comp_data = {
                                "参数名": disp_keys,
                                f"模型 A ({arch_a})": [cfg1.get(k, "-") for k in disp_keys],
                                f"模型 B ({arch_b})": [cfg2.get(k, "-") for k in disp_keys]
                            }
                            st.dataframe(pd.DataFrame(comp_data), use_container_width=True)
                        # -----------------------

                        with st.spinner("正在对比推理中..."):
                            df_a, m_a = run_infer(model_a, audio_files)
                            df_b, m_b = run_infer(model_b, audio_files)

                        st.subheader("📊 核心指标对比")
                        cc1, cc2, cc3, cc4, cc5 = st.columns(5)
                        cc1.metric("样本数", m_a["samples"])
                        cc2.metric(f"A 蚊子检出", m_a["mosquito"], delta_color="inverse")
                        cc3.metric(f"B 蚊子检出", m_b["mosquito"], delta_color="inverse")
                        cc4.metric(f"A 读取失败", m_a["read_fail"])
                        cc5.metric(f"B 读取失败", m_b["read_fail"])

                        st.write(f"**模型 A ({arch_a}) 准确率：** {m_a['acc_str']}   |   **模型 B ({arch_b}) 准确率：** {m_b['acc_str']}")

                        if st.button("💾 记录本次对比结果", key="btn_save_cmp", type="primary"):
                            st.session_state["history"].insert(0, {
                                "时间": datetime.now().strftime("%H:%M:%S"),
                                "模式": "对比",
                                "结构": f"{arch_a} vs {arch_b}",
                                "模型名称": f"{model_file_a.name} | {model_file_b.name}",
                                "样本数": m_a["samples"],
                                "蚊子数": f"{m_a['mosquito']} | {m_b['mosquito']}",
                                "准确率": f"{m_a['acc_str']} | {m_b['acc_str']}",
                                "读取失败": f"{m_a['read_fail']} | {m_b['read_fail']}",
                            })
                            st.success("已保存！")

                        st.subheader("🔍 逐文件差异对比")
                        cmp = pd.merge(
                            df_a[["文件名", "真实标签", "真实idx", "预测标签", "预测idx", "置信度", "判定"]].rename(
                                columns={"预测标签": "A预测", "预测idx": "A预测idx", "置信度": "A置信度", "判定": "A判定"}
                            ),
                            df_b[["文件名", "预测标签", "预测idx", "置信度", "判定"]].rename(
                                columns={"预测标签": "B预测", "预测idx": "B预测idx", "置信度": "B置信度", "判定": "B判定"}
                            ),
                            on="文件名",
                            how="inner"
                        )
                        cmp["A置信度"] = (cmp["A置信度"] * 100).map(lambda x: f"{x:.1f}%")
                        cmp["B置信度"] = (cmp["B置信度"] * 100).map(lambda x: f"{x:.1f}%")
                        cmp["预测是否不同"] = np.where(
                            (cmp["A预测idx"] != -1) & (cmp["B预测idx"] != -1) & (cmp["A预测idx"] != cmp["B预测idx"]),
                            "✅ 不同",
                            "—"
                        )

                        only_diff = st.checkbox("只显示两模型预测不同的样本", value=True, key="chk_only_diff")
                        show_cmp = cmp[cmp["预测是否不同"] == "✅ 不同"] if only_diff else cmp

                        st.dataframe(
                            show_cmp[["文件名", "真实标签", 
                                      "A预测", "A置信度", "A判定", 
                                      "B预测", "B置信度", "B判定", 
                                      "预测是否不同"]],
                            use_container_width=True,
                            hide_index=True
                        )
                except Exception as e:
                    st.error(f"发生运行时错误: {e}")
                    st.exception(e)

# ================= 8. 历史记录 =================
if len(st.session_state["history"]) > 0:
    st.markdown("### 📜 模型测试历史记录")
    history_df = pd.DataFrame(st.session_state["history"])
    st.dataframe(history_df, use_container_width=True, hide_index=True)

    if st.button("清空历史记录", key="btn_clear_history"):
        st.session_state["history"] = []
        st.rerun()
