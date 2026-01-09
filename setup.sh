#!/bin/bash
# Multi-LLM MCP 서버 설치 스크립트
# OAuth 로그인 방식 지원 (API 키 불필요)

set -e

echo "🚀 Multi-LLM MCP 서버 설치 중..."
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Python 버전 확인
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3가 필요합니다"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "📦 Python 버전: $PYTHON_VERSION"

# Node.js 확인
if ! command -v npm &> /dev/null; then
    echo "❌ Node.js/npm이 필요합니다 (CLI 설치용)"
    exit 1
fi

echo "📦 Node.js 버전: $(node --version)"

# 가상환경 생성
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Python 가상환경 생성 중..."
    python3 -m venv venv
fi

source venv/bin/activate

# Python 의존성 설치
echo ""
echo "📦 Python 의존성 설치 중..."
pip install --upgrade pip -q
pip install -e . -q

# Codex CLI 설치
echo ""
echo "📦 Codex CLI 설치 중 (GPT용)..."
if ! command -v codex &> /dev/null; then
    npm install -g @openai/codex 2>/dev/null || {
        echo "⚠️  Codex CLI 설치 실패 - 수동 설치 필요: npm install -g @openai/codex"
    }
else
    echo "✅ Codex CLI 이미 설치됨"
fi

# Gemini CLI 설치
echo ""
echo "📦 Gemini CLI 설치 중 (Gemini용)..."
if ! command -v gemini &> /dev/null; then
    npm install -g @google/gemini-cli 2>/dev/null || {
        echo "⚠️  Gemini CLI 설치 실패 - 수동 설치 필요: npm install -g @google/gemini-cli"
    }
else
    echo "✅ Gemini CLI 이미 설치됨"
fi

echo ""
echo "============================================"
echo "✅ 설치 완료!"
echo "============================================"
echo ""
echo "📋 다음 단계: CLI 로그인"
echo ""
echo "1. GPT 로그인 (ChatGPT 계정):"
echo "   $ codex"
echo "   → 'Sign in with ChatGPT' 선택"
echo ""
echo "2. Gemini 로그인 (Google 계정):"
echo "   $ gemini"
echo "   → 'Login with Google' 선택"
echo ""
echo "3. Claude Code 설정에 MCP 서버 추가:"
echo "   프로젝트 루트에 .mcp.json 파일 생성:"
echo ""
cat << EOF
{
  "mcpServers": {
    "multi-llm": {
      "command": "$SCRIPT_DIR/venv/bin/python",
      "args": ["-m", "src.server"],
      "cwd": "$SCRIPT_DIR"
    }
  }
}
EOF
echo ""
echo "4. Claude Code 재시작"
echo ""
echo "============================================"
echo "💡 API 키 없이 로그인만으로 사용 가능합니다!"
echo "============================================"
