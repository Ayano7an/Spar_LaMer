#!/bin/zsh

# La Mer 快速启动脚本
# 文件路径

SCRIPT_PATH="" # 绝对路径
SCRIPT_DIR=$(dirname "$SCRIPT_PATH")

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "${GREEN}🌊 启动 La Mer...${NC}"

# 检查文件是否存在
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "${RED}错误: 找不到文件 $SCRIPT_PATH${NC}"
    exit 1
fi

# 进入脚本目录
cd "$SCRIPT_DIR" || exit 1

# 检查并创建虚拟环境
if [ ! -d ".venv" ]; then
    echo "${GREEN}创建虚拟环境...${NC}"
    python3 -m venv .venv
fi

# 激活虚拟环境
echo "${GREEN}激活虚拟环境...${NC}"
source .venv/bin/activate

# 安装/更新依赖
echo "${GREEN}检查依赖...${NC}"
pip install -q streamlit pandas plotly

# 启动Streamlit
echo "${GREEN}✅ 启动成功！${NC}"
echo "${GREEN}访问地址: http://localhost:8501${NC}"
echo "${GREEN}按 Ctrl+C 停止服务${NC}"

streamlit run "$SCRIPT_PATH" --server.port 8501