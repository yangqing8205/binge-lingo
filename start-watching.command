#!/bin/bash
# BingeLingo 监听启动器 —— 双击运行。
# 关闭此终端窗口即停止监听（不会开机自启、不会后台常驻）。

# 切到脚本所在目录（即项目根目录），无论从哪儿双击都正确定位。
cd "$(dirname "$0")" || exit 1

echo "======================================"
echo "  BingeLingo 截图监听"
echo "  项目目录: $(pwd)"
echo "  启动时会先问今天看什么剧（可回车跳过）"
echo "  关闭本窗口即停止监听"
echo "======================================"
echo

# 优先用项目虚拟环境里的 Python。
if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
else
    echo "⚠️  没找到 .venv，改用系统 python3。"
    echo "   如需重建：python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt"
    echo
    PY="python3"
fi

# 前台运行；Ctrl-C 或关窗口都会终止它。
exec "$PY" main.py
