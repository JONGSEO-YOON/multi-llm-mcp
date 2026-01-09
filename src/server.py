#!/usr/bin/env python3
"""
Multi-LLM MCP Server
Claude Code에서 GPT와 Gemini를 역할별 Sub Agent로 사용할 수 있게 해주는 MCP 서버

역할 분담:
- Oracle (GPT o1/o3): 고급 추론, 아키텍처 설계, 복잡한 문제 해결
- Frontend Designer (Gemini): UI/UX 코드 작성, 컴포넌트 설계
- Document Writer (Gemini): README, 문서, 주석 작성
- Multimodal Looker (Gemini): 이미지/스크린샷 분석
- Librarian/Explore (Claude): 코드베이스 탐색 (기본 역할)

인증 방식:
- GPT: Codex CLI (ChatGPT 계정 로그인) 또는 API 키
- Gemini: Gemini CLI (Google 계정 로그인) 또는 API 키
"""

import os
import asyncio
import subprocess
import shutil
import base64
from typing import Optional
from dotenv import load_dotenv

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Load environment variables
load_dotenv()

# Initialize MCP server
server = Server("multi-llm")

# CLI paths
CODEX_PATH = shutil.which("codex")
GEMINI_PATH = shutil.which("gemini")


def has_codex_cli() -> bool:
    return CODEX_PATH is not None


def has_gemini_cli() -> bool:
    return GEMINI_PATH is not None


def has_openai_api_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def has_gemini_api_key() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


# ============================================
# GPT 실행 함수들
# ============================================

async def run_codex(prompt: str, model: str = "o4-mini") -> str:
    """Codex CLI를 통해 GPT에게 질문 (OAuth 인증)"""
    if not has_codex_cli():
        raise RuntimeError("Codex CLI가 설치되어 있지 않습니다. 'npm install -g @openai/codex'로 설치하세요.")

    process = await asyncio.create_subprocess_exec(
        CODEX_PATH, "exec", prompt,
        "--model", model,
        "--quiet",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        if "not logged in" in error_msg.lower() or "auth" in error_msg.lower():
            raise RuntimeError(
                "Codex CLI에 로그인이 필요합니다.\n"
                "터미널에서 'codex' 명령어를 실행하고 ChatGPT 계정으로 로그인하세요."
            )
        raise RuntimeError(f"Codex CLI 오류: {error_msg}")

    return stdout.decode().strip()


async def run_openai_api(prompt: str, model: str = "gpt-4o", system_prompt: str = "",
                         temperature: float = 0.7, max_tokens: int = 4096) -> str:
    """OpenAI API를 직접 호출 (API 키 인증)"""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")

    client = OpenAI(api_key=api_key)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # o1/o3 모델은 system prompt 미지원
    if model.startswith("o1") or model.startswith("o3"):
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        messages = [{"role": "user", "content": full_prompt}]
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_tokens
        )
    else:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

    return response.choices[0].message.content


# ============================================
# Gemini 실행 함수들
# ============================================

async def run_gemini(prompt: str) -> str:
    """Gemini CLI를 통해 Gemini에게 질문 (OAuth 인증)"""
    if not has_gemini_cli():
        raise RuntimeError("Gemini CLI가 설치되어 있지 않습니다. 'npm install -g @google/gemini-cli'로 설치하세요.")

    process = await asyncio.create_subprocess_exec(
        GEMINI_PATH, "-p", prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        if "not logged in" in error_msg.lower() or "auth" in error_msg.lower() or "login" in error_msg.lower():
            raise RuntimeError(
                "Gemini CLI에 로그인이 필요합니다.\n"
                "터미널에서 'gemini' 명령어를 실행하고 Google 계정으로 로그인하세요."
            )
        raise RuntimeError(f"Gemini CLI 오류: {error_msg}")

    return stdout.decode().strip()


async def run_gemini_api(prompt: str, model: str = "gemini-1.5-flash",
                         temperature: float = 0.7, max_tokens: int = 4096,
                         image_path: str = None) -> str:
    """Gemini API를 직접 호출 (API 키 인증, 이미지 지원)"""
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

    genai.configure(api_key=api_key)
    model_instance = genai.GenerativeModel(model)

    content = [prompt]

    # 이미지가 있으면 추가
    if image_path and os.path.exists(image_path):
        import PIL.Image
        img = PIL.Image.open(image_path)
        content = [prompt, img]

    response = model_instance.generate_content(
        content,
        generation_config={"temperature": temperature, "max_output_tokens": max_tokens}
    )

    return response.text


# ============================================
# 역할별 실행 함수들
# ============================================

async def run_gpt(prompt: str, model: str = "gpt-5.2", system_prompt: str = "", use_api: bool = False) -> tuple[str, str]:
    """GPT 실행 (CLI 우선) - 기본 모델: GPT-5.2"""
    if use_api or (not has_codex_cli() and has_openai_api_key()):
        result = await run_openai_api(prompt, model, system_prompt)
        return result, f"OpenAI API ({model})"
    elif has_codex_cli():
        # CLI에서도 gpt-5.2 사용
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        result = await run_codex(full_prompt, model)
        return result, f"Codex CLI ({model})"
    elif has_openai_api_key():
        result = await run_openai_api(prompt, model, system_prompt)
        return result, f"OpenAI API ({model})"
    else:
        raise RuntimeError("GPT 사용 불가: Codex CLI 로그인 또는 API 키 설정 필요")


async def run_gemini_agent(prompt: str, model: str = "gemini-3", use_api: bool = False, image_path: str = None) -> tuple[str, str]:
    """Gemini 실행 (CLI 우선, 이미지는 API만) - 기본 모델: Gemini 3"""
    # 이미지가 있으면 API 강제
    if image_path:
        if not has_gemini_api_key():
            raise RuntimeError("이미지 분석은 API 키가 필요합니다. GEMINI_API_KEY를 설정하세요.")
        result = await run_gemini_api(prompt, model, image_path=image_path)
        return result, f"Gemini API ({model}) + Image"

    if use_api or (not has_gemini_cli() and has_gemini_api_key()):
        result = await run_gemini_api(prompt, model)
        return result, f"Gemini API ({model})"
    elif has_gemini_cli():
        result = await run_gemini(prompt)
        return result, "Gemini CLI (gemini-3)"
    elif has_gemini_api_key():
        result = await run_gemini_api(prompt, model)
        return result, f"Gemini API ({model})"
    else:
        raise RuntimeError("Gemini 사용 불가: Gemini CLI 로그인 또는 API 키 설정 필요")


# ============================================
# MCP 도구 정의
# ============================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """사용 가능한 도구 목록 반환"""
    return [
        # ========== Oracle (GPT o1/o3) ==========
        Tool(
            name="ask_gpt",
            description="""GPT 모델에게 질문합니다.

인증 방식 (우선순위):
1. Codex CLI (ChatGPT 계정 로그인) - API 키 불필요
2. OpenAI API 키 - .env에 OPENAI_API_KEY 설정

Codex CLI 로그인: 터미널에서 'codex' 실행 후 ChatGPT 계정으로 로그인

기본 모델: GPT-5.2""",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "GPT에게 보낼 질문/프롬프트"
                    },
                    "model": {
                        "type": "string",
                        "description": "사용할 모델 (기본값: gpt-5.2)",
                        "enum": ["gpt-5.2", "gpt-5", "gpt-4o", "gpt-4o-mini"],
                        "default": "gpt-5.2"
                    },
                    "use_api": {
                        "type": "boolean",
                        "description": "True면 API 키 사용, False면 Codex CLI 사용 (기본값: False - CLI 우선)",
                        "default": False
                    }
                },
                "required": ["prompt"]
            }
        ),
        Tool(
            name="oracle",
            description="""🔮 Oracle - 고급 추론 에이전트 (GPT-5.2)

복잡한 문제 해결, 아키텍처 설계, 알고리즘 설계 등 깊은 추론이 필요한 작업에 사용합니다.
GPT-5.2를 사용하여 step-by-step으로 분석합니다.

사용 예시:
- 복잡한 시스템 아키텍처 설계
- 알고리즘 최적화 방안 분석
- 기술 선택 의사결정
- 버그의 근본 원인 분석
- 리팩토링 전략 수립""",
            inputSchema={
                "type": "object",
                "properties": {
                    "problem": {
                        "type": "string",
                        "description": "해결해야 할 복잡한 문제 또는 설계 요청"
                    },
                    "context": {
                        "type": "string",
                        "description": "관련 코드, 현재 상황, 제약 조건 등 컨텍스트"
                    },
                    "model": {
                        "type": "string",
                        "description": "사용할 모델",
                        "enum": ["gpt-5.2", "gpt-5", "gpt-4o"],
                        "default": "gpt-5.2"
                    }
                },
                "required": ["problem"]
            }
        ),

        # ========== Gemini 에이전트들 ==========
        Tool(
            name="ask_gemini",
            description="""Gemini 모델에게 질문합니다.

인증 방식 (우선순위):
1. Gemini CLI (Google 계정 로그인) - API 키 불필요
2. Gemini API 키 - .env에 GEMINI_API_KEY 설정

Gemini CLI 로그인: 터미널에서 'gemini' 실행 후 Google 계정으로 로그인

기본 모델: Gemini 3""",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Gemini에게 보낼 질문/프롬프트"
                    },
                    "model": {
                        "type": "string",
                        "description": "사용할 모델 (기본값: gemini-3)",
                        "enum": ["gemini-3", "gemini-2.5-pro", "gemini-2.0-flash"],
                        "default": "gemini-3"
                    },
                    "use_api": {
                        "type": "boolean",
                        "description": "True면 API 키 사용, False면 Gemini CLI 사용 (기본값: False - CLI 우선)",
                        "default": False
                    }
                },
                "required": ["prompt"]
            }
        ),
        Tool(
            name="frontend_designer",
            description="""🎨 Frontend Designer - UI/UX 코드 작성 에이전트 (Gemini)

프론트엔드 UI/UX 코드를 작성합니다. React, Vue, HTML/CSS, Tailwind 등
다양한 프레임워크와 스타일링을 지원합니다.

사용 예시:
- React 컴포넌트 작성
- Tailwind CSS 스타일링
- 반응형 레이아웃 구현
- 애니메이션 효과 추가
- 접근성(a11y) 개선
- 디자인 시스템 컴포넌트 생성""",
            inputSchema={
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "만들고 싶은 UI/UX 컴포넌트 또는 페이지 설명"
                    },
                    "framework": {
                        "type": "string",
                        "description": "사용할 프레임워크",
                        "enum": ["react", "vue", "svelte", "html", "nextjs", "flutter"],
                        "default": "react"
                    },
                    "styling": {
                        "type": "string",
                        "description": "스타일링 방식",
                        "enum": ["tailwind", "css", "styled-components", "scss", "emotion"],
                        "default": "tailwind"
                    },
                    "existing_code": {
                        "type": "string",
                        "description": "기존 코드 (수정/개선 시)"
                    }
                },
                "required": ["request"]
            }
        ),
        Tool(
            name="document_writer",
            description="""📝 Document Writer - 문서 작성 에이전트 (Gemini)

README, API 문서, 주석, 기술 문서 등을 작성합니다.
코드를 분석하고 이해하기 쉬운 문서를 생성합니다.

사용 예시:
- README.md 작성
- API 문서 생성
- 코드 주석 추가
- 기술 스펙 문서 작성
- CHANGELOG 생성
- 사용자 가이드 작성""",
            inputSchema={
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "작성할 문서의 종류와 요구사항"
                    },
                    "code_or_context": {
                        "type": "string",
                        "description": "문서화할 코드 또는 프로젝트 컨텍스트"
                    },
                    "doc_type": {
                        "type": "string",
                        "description": "문서 종류",
                        "enum": ["readme", "api", "comment", "spec", "changelog", "guide"],
                        "default": "readme"
                    },
                    "language": {
                        "type": "string",
                        "description": "문서 작성 언어",
                        "enum": ["korean", "english"],
                        "default": "korean"
                    }
                },
                "required": ["request"]
            }
        ),
        Tool(
            name="multimodal_look",
            description="""👁️ Multimodal Looker - 이미지 분석 에이전트 (Gemini)

스크린샷, UI 이미지, 다이어그램 등을 분석합니다.
이미지를 보고 코드 생성, 버그 발견, 디자인 피드백 등을 제공합니다.

⚠️ 이 기능은 Gemini API 키가 필요합니다 (CLI 미지원)

사용 예시:
- 스크린샷에서 UI 코드 생성
- UI 버그/이슈 발견
- 디자인 피드백 제공
- 아키텍처 다이어그램 분석
- 에러 스크린샷 분석""",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "분석할 이미지 파일 경로 (절대 경로)"
                    },
                    "request": {
                        "type": "string",
                        "description": "이미지에 대해 분석하거나 요청할 내용"
                    },
                    "task_type": {
                        "type": "string",
                        "description": "작업 유형",
                        "enum": ["generate_code", "find_bugs", "design_feedback", "analyze", "extract_text"],
                        "default": "analyze"
                    }
                },
                "required": ["image_path", "request"]
            }
        ),

        # ========== 비교 및 유틸리티 ==========
        Tool(
            name="compare_models",
            description="""같은 질문을 GPT와 Gemini 모두에게 보내고 결과를 비교합니다.

두 모델의 응답을 병렬로 받아서 비교할 수 있습니다.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "두 모델에게 보낼 공통 질문"
                    }
                },
                "required": ["prompt"]
            }
        ),
        Tool(
            name="check_status",
            description="GPT와 Gemini의 인증 상태를 확인합니다.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="login_guide",
            description="Codex CLI와 Gemini CLI 로그인 방법을 안내합니다.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """도구 실행"""

    try:
        if name == "ask_gpt":
            return await _ask_gpt(arguments)
        elif name == "oracle":
            return await _oracle(arguments)
        elif name == "ask_gemini":
            return await _ask_gemini(arguments)
        elif name == "frontend_designer":
            return await _frontend_designer(arguments)
        elif name == "document_writer":
            return await _document_writer(arguments)
        elif name == "multimodal_look":
            return await _multimodal_look(arguments)
        elif name == "compare_models":
            return await _compare_models(arguments)
        elif name == "check_status":
            return await _check_status()
        elif name == "login_guide":
            return await _login_guide()
        else:
            return [TextContent(type="text", text=f"알 수 없는 도구: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ 오류: {str(e)}")]


# ============================================
# 도구 구현
# ============================================

async def _ask_gpt(args: dict) -> list[TextContent]:
    """GPT에게 질문"""
    prompt = args["prompt"]
    model = args.get("model", "gpt-4o")
    use_api = args.get("use_api", False)

    result, method = await run_gpt(prompt, model, use_api=use_api)

    return [TextContent(
        type="text",
        text=f"## GPT 응답\n**방식**: {method}\n\n---\n\n{result}"
    )]


async def _oracle(args: dict) -> list[TextContent]:
    """Oracle - 고급 추론 에이전트"""
    problem = args["problem"]
    context = args.get("context", "")
    model = args.get("model", "gpt-5.2")

    system_prompt = """You are Oracle, an expert reasoning agent specialized in:
- Complex system architecture design
- Algorithm optimization and analysis
- Technical decision making
- Root cause analysis for bugs
- Refactoring strategy planning

Approach every problem with step-by-step reasoning. Consider multiple perspectives,
trade-offs, and edge cases. Provide actionable recommendations with clear justifications."""

    full_prompt = f"""## Problem
{problem}

## Context
{context if context else "No additional context provided."}

Please analyze this problem step by step and provide your recommendations."""

    result, method = await run_gpt(full_prompt, model, system_prompt)

    return [TextContent(
        type="text",
        text=f"## 🔮 Oracle 분석 결과\n**모델**: {method}\n\n---\n\n{result}"
    )]


async def _ask_gemini(args: dict) -> list[TextContent]:
    """Gemini에게 질문"""
    prompt = args["prompt"]
    model = args.get("model", "gemini-1.5-flash")
    use_api = args.get("use_api", False)

    result, method = await run_gemini_agent(prompt, model, use_api=use_api)

    return [TextContent(
        type="text",
        text=f"## Gemini 응답\n**방식**: {method}\n\n---\n\n{result}"
    )]


async def _frontend_designer(args: dict) -> list[TextContent]:
    """Frontend Designer - UI/UX 코드 작성 에이전트"""
    request = args["request"]
    framework = args.get("framework", "react")
    styling = args.get("styling", "tailwind")
    existing_code = args.get("existing_code", "")

    prompt = f"""You are a Frontend Designer agent specialized in creating beautiful,
accessible, and responsive UI/UX code.

## Request
{request}

## Technical Stack
- Framework: {framework}
- Styling: {styling}

{f"## Existing Code to Modify/Improve{chr(10)}{existing_code}" if existing_code else ""}

Please generate clean, well-structured code following best practices for the specified stack.
Include:
1. Complete, working code
2. Brief explanation of key design decisions
3. Accessibility considerations (if applicable)
4. Responsive design notes (if applicable)"""

    result, method = await run_gemini_agent(prompt)

    return [TextContent(
        type="text",
        text=f"## 🎨 Frontend Designer 결과\n**방식**: {method}\n**Framework**: {framework} + {styling}\n\n---\n\n{result}"
    )]


async def _document_writer(args: dict) -> list[TextContent]:
    """Document Writer - 문서 작성 에이전트"""
    request = args["request"]
    code_or_context = args.get("code_or_context", "")
    doc_type = args.get("doc_type", "readme")
    language = args.get("language", "korean")

    doc_type_map = {
        "readme": "README.md",
        "api": "API Documentation",
        "comment": "Code Comments",
        "spec": "Technical Specification",
        "changelog": "CHANGELOG",
        "guide": "User Guide"
    }

    lang_instruction = "Write in Korean (한국어로 작성)" if language == "korean" else "Write in English"

    prompt = f"""You are a Document Writer agent specialized in creating clear,
comprehensive technical documentation.

## Document Type
{doc_type_map.get(doc_type, doc_type)}

## Request
{request}

## Code/Context
{code_or_context if code_or_context else "No code provided."}

## Language
{lang_instruction}

Please write professional documentation that is:
1. Clear and well-organized
2. Complete with all necessary sections
3. Easy to understand for the target audience
4. Following standard documentation conventions"""

    result, method = await run_gemini_agent(prompt)

    return [TextContent(
        type="text",
        text=f"## 📝 Document Writer 결과\n**방식**: {method}\n**문서 유형**: {doc_type_map.get(doc_type, doc_type)}\n\n---\n\n{result}"
    )]


async def _multimodal_look(args: dict) -> list[TextContent]:
    """Multimodal Looker - 이미지 분석 에이전트"""
    image_path = args["image_path"]
    request = args["request"]
    task_type = args.get("task_type", "analyze")

    if not os.path.exists(image_path):
        return [TextContent(
            type="text",
            text=f"❌ 이미지 파일을 찾을 수 없습니다: {image_path}"
        )]

    task_instructions = {
        "generate_code": "Generate code to recreate this UI/design. Be precise with layouts, colors, and spacing.",
        "find_bugs": "Analyze this screenshot for UI bugs, visual issues, or UX problems. List all issues found.",
        "design_feedback": "Provide detailed design feedback including improvements for aesthetics, usability, and accessibility.",
        "analyze": "Analyze and describe what you see in this image in detail.",
        "extract_text": "Extract and transcribe all text visible in this image."
    }

    prompt = f"""{task_instructions.get(task_type, task_instructions["analyze"])}

## User Request
{request}"""

    result, method = await run_gemini_agent(prompt, image_path=image_path)

    return [TextContent(
        type="text",
        text=f"## 👁️ Multimodal Looker 결과\n**방식**: {method}\n**작업**: {task_type}\n\n---\n\n{result}"
    )]


async def _compare_models(args: dict) -> list[TextContent]:
    """두 모델 비교"""
    prompt = args["prompt"]

    gpt_task = run_gpt(prompt, "gpt-5.2")
    gemini_task = run_gemini_agent(prompt, "gemini-3")

    (gpt_result, gpt_method), (gemini_result, gemini_method) = await asyncio.gather(gpt_task, gemini_task)

    combined = f"""# 모델 비교 결과

## 질문
{prompt}

---

## GPT 응답
**방식**: {gpt_method}

{gpt_result}

---

## Gemini 응답
**방식**: {gemini_method}

{gemini_result}
"""

    return [TextContent(type="text", text=combined)]


async def _check_status() -> list[TextContent]:
    """인증 상태 확인"""
    status_lines = ["# 인증 상태\n"]

    # GPT 상태
    status_lines.append("## GPT (OpenAI) - Oracle, ask_gpt")
    if has_codex_cli():
        status_lines.append("✅ Codex CLI 설치됨")
        status_lines.append("   → 'codex' 명령어로 ChatGPT 계정 로그인 가능")
    else:
        status_lines.append("❌ Codex CLI 미설치")
        status_lines.append("   → 'npm install -g @openai/codex'로 설치")

    if has_openai_api_key():
        status_lines.append("✅ OPENAI_API_KEY 설정됨")
    else:
        status_lines.append("⚪ OPENAI_API_KEY 미설정 (선택사항)")

    status_lines.append("")

    # Gemini 상태
    status_lines.append("## Gemini (Google) - Frontend Designer, Document Writer, Multimodal Looker")
    if has_gemini_cli():
        status_lines.append("✅ Gemini CLI 설치됨")
        status_lines.append("   → 'gemini' 명령어로 Google 계정 로그인 가능")
    else:
        status_lines.append("❌ Gemini CLI 미설치")
        status_lines.append("   → 'npm install -g @google/gemini-cli'로 설치")

    if has_gemini_api_key():
        status_lines.append("✅ GEMINI_API_KEY 설정됨 (Multimodal 기능 사용 가능)")
    else:
        status_lines.append("⚠️ GEMINI_API_KEY 미설정 (Multimodal 기능 제한)")

    return [TextContent(type="text", text="\n".join(status_lines))]


async def _login_guide() -> list[TextContent]:
    """로그인 가이드"""
    guide = """# CLI 로그인 가이드

## GPT - Codex CLI 로그인

1. 터미널을 열고 다음 명령어 실행:
   ```bash
   codex
   ```

2. "Sign in with ChatGPT" 선택

3. 브라우저에서 ChatGPT 계정으로 로그인

4. 로그인 완료 후 터미널로 돌아가면 자동으로 인증됨

**지원 플랜**: ChatGPT Plus, Pro, Team, Edu, Enterprise
**사용 가능한 에이전트**: Oracle, ask_gpt

---

## Gemini - Gemini CLI 로그인

1. 터미널을 열고 다음 명령어 실행:
   ```bash
   gemini
   ```

2. "Login with Google" 선택

3. 브라우저에서 Google 계정으로 로그인

4. 로그인 완료 후 터미널로 돌아가면 자동으로 인증됨

**무료 사용량**: 60 요청/분, 1,000 요청/일
**사용 가능한 에이전트**: Frontend Designer, Document Writer, ask_gemini

---

## Multimodal Looker (이미지 분석)

이미지 분석 기능은 **Gemini API 키**가 필요합니다:

1. https://aistudio.google.com/app/apikey 에서 API 키 발급
2. `.env` 파일에 추가:
   ```
   GEMINI_API_KEY=your-api-key-here
   ```

---

## 참고

- 한번 로그인하면 토큰이 저장되어 이후에는 자동으로 인증됩니다
- CLI 로그인과 API 키를 동시에 설정해도 됩니다 (CLI 우선)
"""
    return [TextContent(type="text", text=guide)]


def main():
    """메인 진입점"""
    import asyncio
    asyncio.run(run_server())


async def run_server():
    """서버 실행"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    main()
