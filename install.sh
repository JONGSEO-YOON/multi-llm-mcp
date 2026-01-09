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

# 전역 CLAUDE.md에 Sub Agent 지시 추가
CLAUDE_MD="$HOME/CLAUDE.md"
SUB_AGENT_INSTRUCTIONS='
## Multi-LLM Sub Agents

다음 MCP 도구들을 상황에 맞게 **자동으로** 사용하세요:

### 🔮 Oracle (GPT-5.2) - `mcp__multi-llm__oracle`
**사용 시점**: 복잡한 추론, 아키텍처 설계, 알고리즘 설계, 기술 의사결정이 필요할 때
- 시스템 아키텍처 설계 요청
- 알고리즘 최적화 분석
- 복잡한 버그의 근본 원인 분석
- 리팩토링 전략 수립
- 기술 선택 비교

### 🎨 Frontend Designer (Gemini 3) - `mcp__multi-llm__frontend_designer`
**사용 시점**: UI/UX 코드 작성이 필요할 때
- React/Vue/Svelte 컴포넌트 생성
- Tailwind/CSS 스타일링
- 반응형 레이아웃 구현
- 디자인 시스템 컴포넌트

### 📝 Document Writer (Gemini 3) - `mcp__multi-llm__document_writer`
**사용 시점**: 문서 작성이 필요할 때
- README.md 작성
- API 문서 생성
- 코드 주석 추가
- CHANGELOG 작성

### 👁️ Multimodal Looker (Gemini 3) - `mcp__multi-llm__multimodal_look`
**사용 시점**: 이미지/스크린샷 분석이 필요할 때 (API 키 불필요, CLI로 사용 가능)
- UI 스크린샷에서 코드 생성
- 디자인 피드백 제공
- 에러 스크린샷 분석

### 📚 History 관리
- 에이전트 호출 결과는 `history/HISTORY_#.md`에 자동 저장됩니다
- `mcp__multi-llm__set_project_root`: 프로젝트 루트 설정 (히스토리 저장 위치)
- `mcp__multi-llm__get_history`: 최근 작업 히스토리 조회
- `mcp__multi-llm__compact_history`: 오래된 히스토리 압축

### 사용 규칙
1. 위 상황에 해당하면 **자동으로** 해당 도구를 사용
2. 일반적인 코드 탐색, 검색, 편집은 Claude가 직접 수행
3. 도구 사용 전 사용자에게 물어볼 필요 없음
4. **새 프로젝트 시작 시** `set_project_root`로 프로젝트 경로 설정
5. 이전 작업 맥락이 필요하면 `get_history`로 히스토리 확인
'

if [ -f "$CLAUDE_MD" ]; then
    # 이미 Sub Agent 지시가 있는지 확인
    if ! grep -q "Multi-LLM Sub Agents" "$CLAUDE_MD" 2>/dev/null; then
        echo "$SUB_AGENT_INSTRUCTIONS" >> "$CLAUDE_MD"
        echo -e "${GREEN}✓${NC} ~/CLAUDE.md에 Sub Agent 지시 추가됨"
    else
        echo -e "${GREEN}✓${NC} ~/CLAUDE.md에 이미 Sub Agent 지시가 있음"
    fi
else
    echo "$SUB_AGENT_INSTRUCTIONS" > "$CLAUDE_MD"
    echo -e "${GREEN}✓${NC} ~/CLAUDE.md 생성 및 Sub Agent 지시 추가됨"
fi

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
