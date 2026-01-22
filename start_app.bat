@echo off
echo ==========================================
echo   Mosquito Tracker - Windows Start Script
echo ==========================================

cd /d "%~dp0"

REM 1. 检查虚拟环境是否存在
if not exist "venv" (
    echo [INFO] Creating Python virtual environment...
    python -m venv venv
)

REM 2. 激活虚拟环境
call venv\Scripts\activate

REM 3. 安装依赖 (如果 requirements.txt 有更新会自动安装)
echo [INFO] Installing dependencies...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

REM 4. 启动应用
echo [INFO] Starting Streamlit App...
echo [INFO] Access via: http://YOUR_SERVER_IP:8501
streamlit run Home.py --server.port=8501 --server.address=0.0.0.0

pause
