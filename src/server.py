#!/usr/bin/env python3
"""
Multi-LLM MCP Server
Claude Code에서 GPT와 Gemini를 도구로 사용할 수 있게 해주는 MCP 서버

인증 방식:
- GPT: Codex CLI (ChatGPT 계정 로그인) 또는 API 키
- Gemini: Gemini CLI (Google 계정 로그인) 또는 API 키
"""

import os
import asyncio
import subprocess
import shutil
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
    """Codex CLI가 설치되어 있는지 확인"""
    return CODEX_PATH is not None


def has_gemini_cli() -> bool:
    """Gemini CLI가 설치되어 있는지 확인"""
    return GEMINI_PATH is not None


def has_openai_api_key() -> bool:
    """OpenAI API 키가 설정되어 있는지 확인"""
    return bool(os.getenv("OPENAI_API_KEY"))


def has_gemini_api_key() -> bool:
    """Gemini API 키가 설정되어 있는지 확인"""
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


async def run_codex(prompt: str, model: str = "o4-mini") -> str:
    """Codex CLI를 통해 GPT에게 질문 (OAuth 인증)"""
    if not has_codex_cli():
        raise RuntimeError("Codex CLI가 설치되어 있지 않습니다. 'npm install -g @openai/codex'로 설치하세요.")

    # codex exec "prompt" 형식으로 실행
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


async def run_gemini(prompt: str) -> str:
    """Gemini CLI를 통해 Gemini에게 질문 (OAuth 인증)"""
    if not has_gemini_cli():
        raise RuntimeError("Gemini CLI가 설치되어 있지 않습니다. 'npm install -g @google/gemini-cli'로 설치하세요.")

    # gemini -p "prompt" 형식으로 실행 (non-interactive)
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


async def run_openai_api(prompt: str, model: str = "gpt-4o", system_prompt: str = "You are a helpful assistant.",
                         temperature: float = 0.7, max_tokens: int = 4096) -> str:
    """OpenAI API를 직접 호출 (API 키 인증)"""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")

    client = OpenAI(api_key=api_key)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]

    # o1 모델들은 system prompt와 temperature를 지원하지 않음
    if model.startswith("o1") or model.startswith("o3"):
        messages = [{"role": "user", "content": prompt}]
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


async def run_gemini_api(prompt: str, model: str = "gemini-1.5-flash",
                         temperature: float = 0.7, max_tokens: int = 4096) -> str:
    """Gemini API를 직접 호출 (API 키 인증)"""
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

    genai.configure(api_key=api_key)
    model_instance = genai.GenerativeModel(model)

    response = model_instance.generate_content(
        prompt,
        generation_config={"temperature": temperature, "max_output_tokens": max_tokens}
    )

    return response.text


@server.list_tools()
async def list_tools() -> list[Tool]:
    """사용 가능한 도구 목록 반환"""
    return [
        Tool(
            name="ask_gpt",
            description="""GPT 모델에게 질문합니다.

인증 방식 (우선순위):
1. Codex CLI (ChatGPT 계정 로그인) - API 키 불필요
2. OpenAI API 키 - .env에 OPENAI_API_KEY 설정

Codex CLI 로그인: 터미널에서 'codex' 실행 후 ChatGPT 계정으로 로그인

기본 모델: gpt-4o (API) / o4-mini (Codex CLI)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "GPT에게 보낼 질문/프롬프트"
                    },
                    "model": {
                        "type": "string",
                        "description": "사용할 모델 (기본값: gpt-4o 또는 o4-mini)",
                        "enum": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini", "o3-mini", "o4-mini"],
                        "default": "gpt-4o"
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
            name="ask_gemini",
            description="""Gemini 모델에게 질문합니다.

인증 방식 (우선순위):
1. Gemini CLI (Google 계정 로그인) - API 키 불필요
2. Gemini API 키 - .env에 GEMINI_API_KEY 설정

Gemini CLI 로그인: 터미널에서 'gemini' 실행 후 Google 계정으로 로그인

기본 모델: gemini-2.5-pro (CLI) / gemini-1.5-flash (API)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Gemini에게 보낼 질문/프롬프트"
                    },
                    "model": {
                        "type": "string",
                        "description": "사용할 모델 (API 모드에서만 적용)",
                        "enum": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-exp"],
                        "default": "gemini-1.5-flash"
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

    if name == "ask_gpt":
        return await _ask_gpt(arguments)
    elif name == "ask_gemini":
        return await _ask_gemini(arguments)
    elif name == "compare_models":
        return await _compare_models(arguments)
    elif name == "check_status":
        return await _check_status()
    elif name == "login_guide":
        return await _login_guide()
    else:
        return [TextContent(type="text", text=f"알 수 없는 도구: {name}")]


async def _ask_gpt(args: dict) -> list[TextContent]:
    """GPT에게 질문"""
    prompt = args["prompt"]
    model = args.get("model", "gpt-4o")
    use_api = args.get("use_api", False)

    try:
        # API 사용 강제 또는 CLI 없고 API 키 있는 경우
        if use_api or (not has_codex_cli() and has_openai_api_key()):
            result = await run_openai_api(prompt, model)
            method = f"OpenAI API ({model})"
        # CLI 우선
        elif has_codex_cli():
            cli_model = "o4-mini" if model in ["gpt-4o", "gpt-4o-mini"] else model
            result = await run_codex(prompt, cli_model)
            method = f"Codex CLI ({cli_model})"
        # API 키 fallback
        elif has_openai_api_key():
            result = await run_openai_api(prompt, model)
            method = f"OpenAI API ({model})"
        else:
            return [TextContent(
                type="text",
                text="❌ GPT 사용 불가\n\n"
                     "다음 중 하나를 설정하세요:\n"
                     "1. Codex CLI 로그인: 터미널에서 'codex' 실행\n"
                     "2. API 키 설정: .env에 OPENAI_API_KEY 추가"
            )]

        return [TextContent(
            type="text",
            text=f"## GPT 응답\n**방식**: {method}\n\n---\n\n{result}"
        )]

    except Exception as e:
        return [TextContent(type="text", text=f"❌ GPT 오류: {str(e)}")]


async def _ask_gemini(args: dict) -> list[TextContent]:
    """Gemini에게 질문"""
    prompt = args["prompt"]
    model = args.get("model", "gemini-1.5-flash")
    use_api = args.get("use_api", False)

    try:
        # API 사용 강제 또는 CLI 없고 API 키 있는 경우
        if use_api or (not has_gemini_cli() and has_gemini_api_key()):
            result = await run_gemini_api(prompt, model)
            method = f"Gemini API ({model})"
        # CLI 우선
        elif has_gemini_cli():
            result = await run_gemini(prompt)
            method = "Gemini CLI (gemini-2.5-pro)"
        # API 키 fallback
        elif has_gemini_api_key():
            result = await run_gemini_api(prompt, model)
            method = f"Gemini API ({model})"
        else:
            return [TextContent(
                type="text",
                text="❌ Gemini 사용 불가\n\n"
                     "다음 중 하나를 설정하세요:\n"
                     "1. Gemini CLI 로그인: 터미널에서 'gemini' 실행\n"
                     "2. API 키 설정: .env에 GEMINI_API_KEY 추가"
            )]

        return [TextContent(
            type="text",
            text=f"## Gemini 응답\n**방식**: {method}\n\n---\n\n{result}"
        )]

    except Exception as e:
        return [TextContent(type="text", text=f"❌ Gemini 오류: {str(e)}")]


async def _compare_models(args: dict) -> list[TextContent]:
    """두 모델 비교"""
    prompt = args["prompt"]

    # 병렬로 두 모델에 질문
    gpt_task = _ask_gpt({"prompt": prompt})
    gemini_task = _ask_gemini({"prompt": prompt})

    gpt_result, gemini_result = await asyncio.gather(gpt_task, gemini_task)

    combined = f"""# 모델 비교 결과

## 질문
{prompt}

---

{gpt_result[0].text}

---

{gemini_result[0].text}
"""

    return [TextContent(type="text", text=combined)]


async def _check_status() -> list[TextContent]:
    """인증 상태 확인"""
    status_lines = ["# 인증 상태\n"]

    # GPT 상태
    status_lines.append("## GPT (OpenAI)")
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
    status_lines.append("## Gemini (Google)")
    if has_gemini_cli():
        status_lines.append("✅ Gemini CLI 설치됨")
        status_lines.append("   → 'gemini' 명령어로 Google 계정 로그인 가능")
    else:
        status_lines.append("❌ Gemini CLI 미설치")
        status_lines.append("   → 'npm install -g @google/gemini-cli'로 설치")

    if has_gemini_api_key():
        status_lines.append("✅ GEMINI_API_KEY 설정됨")
    else:
        status_lines.append("⚪ GEMINI_API_KEY 미설정 (선택사항)")

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

---

## 참고

- 한번 로그인하면 토큰이 저장되어 이후에는 자동으로 인증됩니다
- API 키 없이 사용 가능합니다
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
