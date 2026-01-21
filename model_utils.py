import torch
import torch.nn as nn
import torchaudio
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
    def __init__(self):
        super().__init__()
        self.cnn_layers = nn.Sequential(
            nn.Conv2d(1, 8, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(8, 16, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
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
    def __init__(self):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d((1, 2)),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d((1, 2)),
        )
        self.lstm = nn.LSTM(
            input_size=64 * 10,
            hidden_size=128,
            num_layers=1,
            batch_first=True,
            bidirectional=True
        )
        self.classifier = nn.Sequential(
            nn.Linear(128 * 2, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 2)
        )

    def forward(self, x):
        x = self.cnn(x)
        x = x.permute(0, 2, 1, 3).contiguous()
        x = x.view(x.size(0), x.size(1), -1)
        out, _ = self.lstm(x)
        feat = out[:, -1, :]
        return self.classifier(feat)

def build_model(arch: str) -> nn.Module:
    if arch == "CNN":
        return SimpleMosquitoCNN()
    elif arch == "CNN-LSTM":
        return SimpleMosquitoCNNLSTM()
    else:
        raise ValueError(f"未知模型结构: {arch}")

# ================= 3. 音频处理 (Torchaudio 版) =================
def process_audio_tensor(waveform, sample_rate):
    """
    使用 torchaudio 处理音频张量
    """
    # 1. 重采样
    if sample_rate != SR:
        resampler = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=SR)
        waveform = resampler(waveform)

    # 2. 转单声道
    if waveform.shape[0] > 1:
        waveform = torch.mean(waveform, dim=0, keepdim=True)
    
    # 3. 长度裁剪/填充
    target_len = int(SR * 1.0)
    current_len = waveform.shape[1]
    
    if current_len < target_len:
        waveform = torch.nn.functional.pad(waveform, (0, target_len - current_len))
    else:
        waveform = waveform[:, :target_len]

    # 4. 提取 MFCC
    # librosa default n_mels=128, log_mels=False (returns coefficients)
    mfcc_transform = torchaudio.transforms.MFCC(
        sample_rate=SR,
        n_mfcc=N_MFCC,
        melkwargs={"n_fft": N_FFT, "hop_length": HOP_LENGTH, "n_mels": 128}
    )
    
    mfcc = mfcc_transform(waveform) # (Channel, n_mfcc, time)
    mfcc = mfcc.squeeze(0).transpose(0, 1) # (time, n_mfcc)
    
    # 5. 调整帧数 (Max Frames)
    if mfcc.shape[0] < MAX_FRAMES:
        pad = torch.zeros((MAX_FRAMES - mfcc.shape[0], N_MFCC))
        mfcc = torch.cat([mfcc, pad], dim=0)
    else:
        mfcc = mfcc[:MAX_FRAMES, :]

    # (1, 1, T, 40)
    tensor = mfcc.unsqueeze(0).unsqueeze(0)
    return tensor

def parse_label_from_filename(filename):
    fname = filename.lower()
    if "pos" in fname or "mosquito" in fname:
        return 0, "🦟 蚊子"
    elif "neg" in fname or "other" in fname or "noise" in fname:
        return 1, "🔇 噪音"
    else:
        return -1, "❓ 未知"

def load_audio_from_uploaded(uploaded_file):
    """
    使用 torchaudio 读取 (支持 wav, mp3 等)
    """
    data = uploaded_file.getvalue()
    
    # torchaudio.load 支持类文件对象吗？部分版本支持，最稳妥是写临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(data)
        tmp_path = f.name

    try:
        # torchaudio 读取返回 (waveform, sample_rate)
        # waveform: (Channel, Time)
        waveform, sr = torchaudio.load(tmp_path)
        return waveform, sr
    except Exception as e:
        raise e
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

# ================= 6. 推理与统计 =================
def run_infer(model: nn.Module, audio_files):
    results = []
    correct_count = 0
    total_labeled = 0

    progress = st.progress(0)

    for i, audio_file in enumerate(audio_files):
        progress.progress((i + 1) / max(len(audio_files), 1))

        try:
            waveform, sr = load_audio_from_uploaded(audio_file)
            input_tensor = process_audio_tensor(waveform, sr)
        except Exception as e:
            true_idx, true_str = parse_label_from_filename(audio_file.name)
            results.append({
                "文件名": audio_file.name,
                "真实标签": true_str,
                "真实idx": true_idx,
                "预测标签": "❌ 读取失败",
                "预测idx": -1,
                "置信度": 0.0,
                "判定": f"Err: {str(e)[:20]}",
            })
            continue

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

    labeled_df = df[(df["真实idx"] != -1) & (df["预测idx"] != -1)].copy()
    if len(labeled_df) > 0:
        cm = pd.crosstab(
            labeled_df["真实idx"],
            labeled_df["预测idx"],
            rownames=["True"],
            colnames=["Pred"],
            dropna=False
        )
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
