# Multi-LLM MCP Server

Claude Code에서 **GPT**와 **Gemini**를 도구로 사용할 수 있게 해주는 MCP 서버입니다.

## 원클릭 설치

```bash
curl -fsSL https://raw.githubusercontent.com/jongseo-yoon/multi-llm-mcp/main/install.sh | bash
```

이 명령어 하나로 설치부터 Claude Code 설정까지 자동으로 완료됩니다!

## 특징

- **OAuth 로그인 지원** - API 키 없이 ChatGPT/Google 계정으로 로그인
- **CLI 우선** - Codex CLI, Gemini CLI를 통한 인증
- **API 키 fallback** - CLI 로그인이 안 되면 API 키 사용 가능
- **다른 서버에 쉽게 적용** - Git clone 후 설치 스크립트 실행만으로 설정 완료

## 제공 도구

### 에이전트 (Sub Agents)
| 도구 | 설명 |
|------|------|
| `oracle` | 고급 추론 에이전트 (GPT-5.2) - 아키텍처 설계, 알고리즘 최적화 |
| `review_implementation` | 구현 검토 에이전트 (GPT-5.2) - 요구사항 충족 여부 검증 |
| `frontend_designer` | UI/UX 코드 작성 (Gemini 3) - React, Vue, Tailwind 등 |
| `document_writer` | 문서 작성 (Gemini 3) - README, API 문서, 주석 |
| `multimodal_look` | 이미지 분석 (Gemini 3) - 스크린샷에서 코드 생성, 버그 발견 |

### 기본 도구
| 도구 | 설명 |
|------|------|
| `ask_gpt` | GPT에게 질문 (Codex CLI 또는 API) |
| `ask_gemini` | Gemini에게 질문 (Gemini CLI 또는 API) |
| `compare_models` | 같은 질문을 두 모델에 보내고 비교 |
| `check_status` | 인증 상태 확인 |
| `login_guide` | 로그인 방법 안내 |

### History 관리
| 도구 | 설명 |
|------|------|
| `set_project_root` | 프로젝트 루트 설정 (히스토리 저장 위치) |
| `get_history` | 최근 작업 히스토리 조회 |
| `compact_history` | 오래된 히스토리 파일 압축 |
| `save_workflow` | 전체 작업 워크플로우 저장 |

> **History 기능**: 워크플로우가 `history/HISTORY_#.md`에 저장됩니다.
> 10개 이상 쌓이면 자동으로 압축됩니다.

## 빠른 시작

### 1. 클론 및 설치

```bash
git clone <your-repo-url> multi-llm-mcp
cd multi-llm-mcp
chmod +x setup.sh
./setup.sh
```

### 2. CLI 로그인 (API 키 불필요!)

**GPT (ChatGPT 계정)**
```bash
codex
# → "Sign in with ChatGPT" 선택
# → 브라우저에서 로그인
```

**Gemini (Google 계정)**
```bash
gemini
# → "Login with Google" 선택
# → 브라우저에서 로그인
```

### 3. Claude Code 설정

프로젝트 루트에 `.mcp.json` 파일 생성:

```json
{
  "mcpServers": {
    "multi-llm": {
      "command": "/path/to/multi-llm-mcp/venv/bin/python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/multi-llm-mcp"
    }
  }
}
```

### 4. Claude Code 재시작

끝! 이제 Claude Code에서 GPT와 Gemini를 사용할 수 있습니다.

## 자동 사용 설정 (CLAUDE.md)

MCP 서버만 설정하면 도구는 사용 가능하지만, Claude가 **자동으로** 사용하지는 않습니다.
자동 사용을 원하면 `CLAUDE.md` 파일을 프로젝트 루트 또는 홈 디렉토리에 추가하세요.

### CLAUDE.md 설정

**프로젝트별 설정**: 프로젝트 루트에 `CLAUDE.md` 생성
**전역 설정**: `~/CLAUDE.md` 생성

```markdown
## Multi-LLM Sub Agents

다음 MCP 도구들을 상황에 맞게 **자동으로** 사용하세요:

### Oracle (GPT-5.2) - `mcp__multi-llm__oracle`
**사용 시점**: 복잡한 추론, 아키텍처 설계, 알고리즘 설계, 기술 의사결정이 필요할 때

### Review Implementation (GPT-5.2) - `mcp__multi-llm__review_implementation`
**사용 시점**: 구현 완료 후 사용자 요구사항 충족 여부 검증이 필요할 때

### Frontend Designer (Gemini 3) - `mcp__multi-llm__frontend_designer`
**사용 시점**: UI/UX 코드 작성이 필요할 때

### Document Writer (Gemini 3) - `mcp__multi-llm__document_writer`
**사용 시점**: 문서 작성이 필요할 때

### Multimodal Looker (Gemini 3) - `mcp__multi-llm__multimodal_look`
**사용 시점**: 이미지/스크린샷 분석이 필요할 때

### 사용 규칙
1. 위 상황에 해당하면 **자동으로** 해당 도구를 사용
2. 일반적인 코드 탐색, 검색, 편집은 Claude가 직접 수행
3. 도구 사용 전 사용자에게 물어볼 필요 없음

### 자동 워크플로우
**코드 구현 완료 시 반드시 review_implementation 실행:**
1. 사용자 요청에 따라 코드 구현 완료
2. **자동으로** `review_implementation` 호출하여 요구사항 충족 여부 검증
3. 피드백 결과에 따라:
   - COMPLETE: 사용자에게 완료 보고
   - INCOMPLETE/NEEDS REVISION: 누락된 부분 자동으로 수정 후 다시 검증
```

### 빠른 설정 (전역)

```bash
cp CLAUDE.md ~/CLAUDE.md
```

이제 모든 프로젝트에서 Claude가 자동으로 GPT/Gemini 에이전트를 활용합니다.

## 사용 예시

Claude Code에서 자연어로 요청:

```
"GPT한테 이 코드 리뷰 좀 부탁해줘"
→ ask_gpt 도구 사용

"Gemini한테 이 알고리즘 최적화 방법 물어봐줘"
→ ask_gemini 도구 사용

"GPT랑 Gemini 둘 다한테 물어보고 비교해줘"
→ compare_models 도구 사용

"인증 상태 확인해줘"
→ check_status 도구 사용
```

## 인증 방식

### 우선순위
1. **CLI 로그인** (추천) - API 키 불필요
2. **API 키** - .env 파일에 설정

### GPT (OpenAI)
- **Codex CLI**: ChatGPT Plus/Pro/Team/Edu/Enterprise 계정 필요
- **API 키**: `OPENAI_API_KEY` 환경 변수

### Gemini (Google)
- **Gemini CLI**: Google 계정 (무료, 60 요청/분)
- **API 키**: `GEMINI_API_KEY` 환경 변수

## 다른 서버에 빠르게 적용

```bash
# 1. 클론
git clone <your-repo> multi-llm-mcp
cd multi-llm-mcp

# 2. 설치 (Python 의존성 + CLI 설치)
./setup.sh

# 3. 로그인
codex   # GPT
gemini  # Gemini

# 4. Claude Code 설정에 추가 (위의 JSON 참고)

# 5. Claude Code 재시작
```

## 선택사항: API 키 설정

CLI 로그인 대신 API 키를 사용하려면:

```bash
cp .env.example .env
# .env 파일 편집하여 API 키 입력
```

```env
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
```

## 지원 모델

### GPT (via Codex CLI)
- `o4-mini` (기본값)
- `o3-mini`
- `o1`, `o1-mini`

### GPT (via API)
- `gpt-4o` (기본값)
- `gpt-4o-mini`
- `gpt-4-turbo`

### Gemini (via CLI)
- `gemini-3` (기본값)
- 이미지 분석 지원 (`@./path/to/image.png` 형식)

### Gemini (via API)
- `gemini-1.5-flash` (기본값, 빠름)
- `gemini-1.5-pro` (고품질)
- `gemini-2.0-flash-exp`

## 이미지 분석 (Multimodal)

Gemini CLI는 이미지를 지원합니다. API 키 없이도 사용 가능합니다.

```
# Gemini CLI로 이미지 분석
"이 스크린샷 분석해줘" + 이미지 경로 전달
→ multimodal_look 도구 사용
```

## 문제 해결

### CLI 로그인 오류
```
Codex CLI에 로그인이 필요합니다.
```
→ 터미널에서 `codex` 실행 후 로그인

### CLI 설치 오류
```bash
# Codex CLI 수동 설치
npm install -g @openai/codex

# Gemini CLI 수동 설치
npm install -g @google/gemini-cli
```

### 상태 확인
Claude Code에서 "인증 상태 확인해줘" 요청

## 라이선스

MIT
