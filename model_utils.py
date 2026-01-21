import torch
import torch.nn as nn
import librosa
import numpy as np
import pandas as pd
import io
import os
import tempfile
import streamlit as st

# ================= 1. 核心配置 =================
SR = 16000
N_MFCC = 40
HOP_LENGTH = 512
N_FFT = 1024
MAX_FRAMES = 32
CLASSES = {0: "🦟 发现蚊子 (Mosquito)", 1: "🔇 安全/噪音 (Other)"}

# ================= 2. 两种模型结构 =================
class SimpleMosquitoCNN(nn.Module):
    """纯 CNN（输入 (B,1,32,40) -> 输出 (B,2)）"""
    def __init__(self):
        super().__init__()
        self.cnn_layers = nn.Sequential(
            nn.Conv2d(1, 8, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),        # (8,16,20)
            nn.Conv2d(8, 16, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),        # (16,8,10)
        )
        self.fc_layers = nn.Sequential(
            nn.Flatten(),
            nn.Linear(16 * 8 * 10, 64),
            nn.ReLU(),
            nn.Linear(64, 2)
        )

    def forward(self, x):
        x = self.cnn_layers(x)
        x = self.fc_layers(x)
        return x

class SimpleMosquitoCNNLSTM(nn.Module):
    """
    CNN-LSTM（已对齐你上传的 checkpoint 特征）
    """
    def __init__(self):
        super().__init__()

        self.cnn = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1),      # cnn.0.*
            nn.BatchNorm2d(32),                  # cnn.1.*
            nn.ReLU(),                           # cnn.2
            nn.MaxPool2d((1, 2)),                # cnn.3  40->20

            nn.Conv2d(32, 64, 3, padding=1),     # cnn.4.*
            nn.BatchNorm2d(64),                  # cnn.5.*
            nn.ReLU(),                           # cnn.6
            nn.MaxPool2d((1, 2)),                # cnn.7  20->10
        )

        self.lstm = nn.LSTM(
            input_size=64 * 10,      # 640
            hidden_size=128,
            num_layers=1,
            batch_first=True,
            bidirectional=True
        )

        self.classifier = nn.Sequential(
            nn.Linear(128 * 2, 128),  # 256->128
            nn.ReLU(),
            nn.Dropout(0.3),          # 关键：保证最终层 index 为 classifier.3
            nn.Linear(128, 2)
        )

    def forward(self, x):
        x = self.cnn(x)                                    # (B,64,32,10)
        x = x.permute(0, 2, 1, 3).contiguous()     # (B,32,64,10)
        x = x.view(x.size(0), x.size(1), -1)       # (B,32,640)

        out, _ = self.lstm(x)                              # (B,32,256)
        feat = out[:, -1, :]                               # (B,256)
        return self.classifier(feat)                       # (B,2)

def build_model(arch: str) -> nn.Module:
    if arch == "CNN":
        return SimpleMosquitoCNN()
    elif arch == "CNN-LSTM":
        return SimpleMosquitoCNNLSTM()
    else:
        raise ValueError(f"未知模型结构: {arch}")

# ================= 3. 音频处理 =================
def process_audio(y, sr):
    """把音频处理成 (1,1,32,40) 的 MFCC 输入张量"""
    target_len = int(sr * 1.0)
    if len(y) < target_len:
        y = np.pad(y, (0, target_len - len(y)))
    else:
        y = y[:target_len]

    mfcc = librosa.feature.mfcc(
        y=y, sr=sr, n_mfcc=N_MFCC, n_fft=N_FFT, hop_length=HOP_LENGTH
    ).T  # (T,40)

    if mfcc.shape[0] < MAX_FRAMES:
        pad = np.zeros((MAX_FRAMES - mfcc.shape[0], N_MFCC), dtype=np.float32)
        mfcc = np.vstack([mfcc, pad])
    else:
        mfcc = mfcc[:MAX_FRAMES, :]

    tensor = torch.tensor(mfcc, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
    return tensor

def parse_label_from_filename(filename):
    fname = filename.lower()
    if "pos" in fname or "mosquito" in fname:
        return 0, "🦟 蚊子"
    elif "neg" in fname or "other" in fname or "noise" in fname:
        return 1, "🔇 噪音"
    else:
        return -1, "❓ 未知"

def load_audio_from_uploaded(uploaded_file, target_sr=SR):
    """
    解决 LibsndfileError
    """
    data = uploaded_file.getvalue()

    # 1) 先尝试 BytesIO
    bio = io.BytesIO(data)
    try:
        bio.seek(0)
        y, sr = librosa.load(bio, sr=target_sr, mono=True)
        return y, sr
    except Exception:
        pass

    # 2) fallback：落盘临时文件再读
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(data)
        tmp_path = f.name

    try:
        y, sr = librosa.load(tmp_path, sr=target_sr, mono=True)
        return y, sr
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

# ================= 5. 模型加载 =================
@st.cache_resource
def load_model_from_bytes(uploaded_file, arch: str):
    device = torch.device("cpu")
    model = build_model(arch).to(device)

    bytes_data = uploaded_file.getvalue()
    buffer = io.BytesIO(bytes_data)

    try:
        # 新 torch: weights_only=True
        try:
            sd = torch.load(buffer, map_location=device, weights_only=True)
        except TypeError:
            buffer.seek(0)
            sd = torch.load(buffer, map_location=device)

        model.load_state_dict(sd)
        model.eval()
        return model, f"✅ 模型加载成功（{arch}）"
    except Exception as e:
        return None, f"❌ 模型加载失败（{arch}）：{e}"

# ================= 6. 推理与统计 (核心函数) =================
def run_infer(model: nn.Module, audio_files):
    results = []
    correct_count = 0
    total_labeled = 0

    progress = st.progress(0)

    for i, audio_file in enumerate(audio_files):
        progress.progress((i + 1) / max(len(audio_files), 1))

        # ---- 读取音频 (容错) ----
        try:
            y, sr = load_audio_from_uploaded(audio_file, target_sr=SR)
        except Exception as e:
            true_idx, true_str = parse_label_from_filename(audio_file.name)
            results.append({
                "文件名": audio_file.name,
                "真实标签": true_str,
                "真实idx": true_idx,
                "预测标签": "❌ 读取失败",
                "预测idx": -1,
                "置信度": 0.0,
                "判定": f"读取失败: {type(e).__name__}",
            })
            continue

        input_tensor = process_audio(y, sr)

        with torch.no_grad():
            output = model(input_tensor)
            probs = torch.softmax(output, dim=1)
            pred_idx = int(torch.argmax(probs).item())
            confidence = float(probs[0, pred_idx].item())

        true_idx, true_str = parse_label_from_filename(audio_file.name)
        pred_str = CLASSES[pred_idx]

        judge = "N/A"
        if true_idx != -1:
            total_labeled += 1
            if true_idx == pred_idx:
                correct_count += 1
                judge = "✅ 正确"
            else:
                judge = "❌ 错误"

        results.append({
            "文件名": audio_file.name,
            "真实标签": true_str,
            "真实idx": true_idx,
            "预测标签": pred_str,
            "预测idx": pred_idx,
            "置信度": confidence,
            "判定": judge,
        })

    progress.empty()

    df = pd.DataFrame(results)

    mosquito_count = int((df["预测idx"] == 0).sum())
    acc_str = "N/A"
    acc_val = None
    if total_labeled > 0:
        acc_val = correct_count / total_labeled
        acc_str = f"{acc_val * 100:.2f}%"

    # 混淆矩阵
    labeled_df = df[(df["真实idx"] != -1) & (df["预测idx"] != -1)].copy()
    if len(labeled_df) > 0:
        cm = pd.crosstab(
            labeled_df["真实idx"],
            labeled_df["预测idx"],
            rownames=["True"],
            colnames=["Pred"],
            dropna=False
        )
        for r in [0, 1]:
            if r not in cm.index:
                cm.loc[r] = 0
        for c in [0, 1]:
            if c not in cm.columns:
                cm[c] = 0
        cm = cm.sort_index().reindex(sorted(cm.columns), axis=1)
    else:
        cm = None

    metrics = {
        "samples": len(df),
        "mosquito": mosquito_count,
        "acc_str": acc_str,
        "acc_val": acc_val,
        "cm": cm,
        "read_fail": int((df["预测idx"] == -1).sum())
    }
    return df, metrics
