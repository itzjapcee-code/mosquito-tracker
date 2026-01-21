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

st.set_page_config(page_title="蚊子识别模型评估看板", page_icon="🦟", layout="wide")

if "history" not in st.session_state:
    st.session_state["history"] = []
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0

st.title("🦟 智能蚊音识别系统 - 性能评估看板")
st.markdown("---")
st.info("💡 **使用说明**: 请先在左侧上传您的 PyTorch 模型文件 (.pth) 和测试音频 (.wav)。")

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
        model_file = st.file_uploader("上传模型文件 (.pth)", type=["pth"], key="single_model_uploader")
    else:
        st.subheader("2️⃣ 上传对比模型")
        cnn_file = st.file_uploader("CNN 模型 (.pth)", type=["pth"], key="cmp_cnn")
        lstm_file = st.file_uploader("CNN-LSTM 模型 (.pth)", type=["pth"], key="cmp_lstm")

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
            if not (cnn_file and lstm_file):
                st.warning("👈 请在左侧上传 CNN 模型和 CNN-LSTM 模型（.pth）开始对比。")
            else:
                try:
                    cnn_model, cnn_msg = load_model_from_bytes(cnn_file, "CNN")
                    lstm_model, lstm_msg = load_model_from_bytes(lstm_file, "CNN-LSTM")

                    if cnn_model is None:
                        st.error(cnn_msg)
                    if lstm_model is None:
                        st.error(lstm_msg)

                    if (cnn_model is not None) and (lstm_model is not None):
                        st.success(cnn_msg)
                        st.success(lstm_msg)

                        with st.spinner("正在对比推理中..."):
                            df_cnn, m_cnn = run_infer(cnn_model, audio_files)
                            df_lstm, m_lstm = run_infer(lstm_model, audio_files)

                        st.subheader("📊 核心指标对比")
                        cc1, cc2, cc3, cc4, cc5 = st.columns(5)
                        cc1.metric("样本数", m_cnn["samples"])
                        cc2.metric("CNN 蚊子检出", m_cnn["mosquito"], delta_color="inverse")
                        cc3.metric("LSTM 蚊子检出", m_lstm["mosquito"], delta_color="inverse")
                        cc4.metric("CNN 读取失败", m_cnn["read_fail"])
                        cc5.metric("LSTM 读取失败", m_lstm["read_fail"])

                        st.write(f"**CNN 准确率：** {m_cnn['acc_str']}   |   **CNN-LSTM 准确率：** {m_lstm['acc_str']}")

                        if st.button("💾 记录本次对比结果", key="btn_save_cmp", type="primary"):
                            st.session_state["history"].insert(0, {
                                "时间": datetime.now().strftime("%H:%M:%S"),
                                "模式": "对比",
                                "结构": "CNN vs CNN-LSTM",
                                "模型名称": f"{cnn_file.name}  |  {lstm_file.name}",
                                "样本数": m_cnn["samples"],
                                "蚊子数": f"{m_cnn['mosquito']} | {m_lstm['mosquito']}",
                                "准确率": f"{m_cnn['acc_str']} | {m_lstm['acc_str']}",
                                "读取失败": f"{m_cnn['read_fail']} | {m_lstm['read_fail']}",
                            })
                            st.success("已保存！")

                        st.subheader("🔍 逐文件差异对比")
                        cmp = pd.merge(
                            df_cnn[["文件名", "真实标签", "真实idx", "预测标签", "预测idx", "置信度", "判定"]].rename(
                                columns={"预测标签": "CNN预测", "预测idx": "CNN预测idx", "置信度": "CNN置信度", "判定": "CNN判定"}
                            ),
                            df_lstm[["文件名", "预测标签", "预测idx", "置信度", "判定"]].rename(
                                columns={"预测标签": "LSTM预测", "预测idx": "LSTM预测idx", "置信度": "LSTM置信度", "判定": "LSTM判定"}
                            ),
                            on="文件名",
                            how="inner"
                        )
                        cmp["CNN置信度"] = (cmp["CNN置信度"] * 100).map(lambda x: f"{x:.1f}%")
                        cmp["LSTM置信度"] = (cmp["LSTM置信度"] * 100).map(lambda x: f"{x:.1f}%")
                        cmp["预测是否不同"] = np.where(
                            (cmp["CNN预测idx"] != -1) & (cmp["LSTM预测idx"] != -1) & (cmp["CNN预测idx"] != cmp["LSTM预测idx"]),
                            "✅ 不同",
                            "—"
                        )

                        only_diff = st.checkbox("只显示两模型预测不同的样本", value=True, key="chk_only_diff")
                        show_cmp = cmp[cmp["预测是否不同"] == "✅ 不同"] if only_diff else cmp

                        st.dataframe(
                            show_cmp[["文件名", "真实标签", 
                                      "CNN预测", "CNN置信度", "CNN判定", 
                                      "LSTM预测", "LSTM置信度", "LSTM判定", 
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
