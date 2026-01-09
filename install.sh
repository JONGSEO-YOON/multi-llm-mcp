#!/bin/bash
# Multi-LLM MCP 원클릭 설치 스크립트
# 사용법: curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/multi-llm-mcp/main/install.sh | bash

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}     ${GREEN}Multi-LLM MCP Server${NC} - 원클릭 설치                    ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}     Claude Code에서 GPT & Gemini 사용하기                 ${BLUE}║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# 설치 경로
INSTALL_DIR="${HOME}/.multi-llm-mcp"
REPO_URL="https://github.com/jongseo-yoon/multi-llm-mcp.git"

# 이전 설치 확인
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}⚠️  이전 설치가 발견되었습니다. 업데이트합니다...${NC}"
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || true
else
    echo -e "${GREEN}📦 설치 중...${NC}"
    git clone "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || {
        echo -e "${RED}❌ Git clone 실패. 레포지토리 URL을 확인하세요.${NC}"
        exit 1
    }
fi

cd "$INSTALL_DIR"

# Python 확인
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3가 필요합니다${NC}"
    exit 1
fi

# Node.js 확인
if ! command -v npm &> /dev/null; then
    echo -e "${RED}❌ Node.js/npm이 필요합니다${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Python $(python3 --version | cut -d' ' -f2)"
echo -e "${GREEN}✓${NC} Node.js $(node --version)"

# Python 가상환경 설정
if [ ! -d "venv" ]; then
    echo -e "${GREEN}📦 Python 가상환경 생성 중...${NC}"
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip -q
pip install -e . -q

# Codex CLI 설치
echo -e "${GREEN}📦 Codex CLI 설치 중...${NC}"
if ! command -v codex &> /dev/null; then
    npm install -g @openai/codex 2>/dev/null || echo -e "${YELLOW}⚠️  Codex CLI 설치 실패 - 나중에 수동 설치 필요${NC}"
fi

# Gemini CLI 설치
echo -e "${GREEN}📦 Gemini CLI 설치 중...${NC}"
if ! command -v gemini &> /dev/null; then
    npm install -g @google/gemini-cli 2>/dev/null || echo -e "${YELLOW}⚠️  Gemini CLI 설치 실패 - 나중에 수동 설치 필요${NC}"
fi

# Claude Code 전역 설정에 MCP 서버 추가
CLAUDE_CONFIG="$HOME/.claude.json"
MCP_CONFIG='{
  "mcpServers": {
    "multi-llm": {
      "command": "'"$INSTALL_DIR"'/venv/bin/python",
      "args": ["-m", "src.server"],
      "cwd": "'"$INSTALL_DIR"'"
    }
  }
}'

echo ""
echo -e "${GREEN}📝 Claude Code 설정 추가 중...${NC}"

# jq가 있으면 사용, 없으면 수동 안내
if command -v jq &> /dev/null; then
    if [ -f "$CLAUDE_CONFIG" ]; then
        # 기존 설정에 병합
        TEMP_FILE=$(mktemp)
        jq --argjson new "$MCP_CONFIG" '
          .mcpServers = (.mcpServers // {}) + $new.mcpServers
        ' "$CLAUDE_CONFIG" > "$TEMP_FILE" && mv "$TEMP_FILE" "$CLAUDE_CONFIG"
        echo -e "${GREEN}✓${NC} Claude Code 전역 설정 업데이트 완료"
    else
        echo "$MCP_CONFIG" | jq '.' > "$CLAUDE_CONFIG"
        echo -e "${GREEN}✓${NC} Claude Code 전역 설정 생성 완료"
    fi
else
    echo -e "${YELLOW}⚠️  jq가 없어서 수동 설정이 필요합니다.${NC}"
    echo ""
    echo "~/.claude.json 또는 프로젝트의 .mcp.json에 다음을 추가하세요:"
    echo ""
    echo -e "${BLUE}$MCP_CONFIG${NC}"
fi

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    ✅ 설치 완료!                          ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}📋 다음 단계: CLI 로그인${NC}"
echo ""
echo -e "   ${BLUE}1. GPT 로그인 (ChatGPT 계정):${NC}"
echo "      $ codex"
echo "      → 'Sign in with ChatGPT' 선택"
echo ""
echo -e "   ${BLUE}2. Gemini 로그인 (Google 계정):${NC}"
echo "      $ gemini"
echo "      → 'Login with Google' 선택"
echo ""
echo -e "   ${BLUE}3. Claude Code 재시작${NC}"
echo ""
echo -e "${GREEN}💡 API 키 없이 로그인만으로 사용 가능합니다!${NC}"
echo ""
echo -e "설치 경로: ${BLUE}$INSTALL_DIR${NC}"
echo ""
