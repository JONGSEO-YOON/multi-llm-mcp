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
import glob
import json
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Load environment variables
load_dotenv()

# Initialize MCP server
server = Server("multi-llm")

# History 설정
HISTORY_DIR_NAME = "history"
MAX_HISTORY_FILES = 10  # 이 개수 이상이면 compaction
COMPACT_INTO = 5  # compaction 시 몇 개로 묶을지


# ============================================
# 비동기 태스크 관리
# ============================================

class TaskManager:
    """백그라운드 에이전트 태스크를 관리하는 클래스

    Claude가 여러 sub agent를 병렬로 실행하고 나중에 결과를 수집할 수 있게 함
    """

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}
        self._results: dict[str, dict] = {}
        self._counter = 0

    def _generate_task_id(self, agent_name: str) -> str:
        """고유 태스크 ID 생성"""
        self._counter += 1
        timestamp = datetime.now().strftime("%H%M%S")
        return f"{agent_name.lower().replace(' ', '_')}_{timestamp}_{self._counter}"

    async def start_task(self, agent_name: str, coro) -> str:
        """에이전트 태스크를 백그라운드로 시작

        Returns:
            task_id: 나중에 결과를 조회할 때 사용할 ID
        """
        task_id = self._generate_task_id(agent_name)

        async def wrapped_task():
            try:
                start_time = datetime.now()
                result = await coro
                end_time = datetime.now()
                self._results[task_id] = {
                    "status": "completed",
                    "agent": agent_name,
                    "result": result,
                    "started_at": start_time.isoformat(),
                    "completed_at": end_time.isoformat(),
                    "duration_seconds": (end_time - start_time).total_seconds()
                }
            except Exception as e:
                self._results[task_id] = {
                    "status": "failed",
                    "agent": agent_name,
                    "error": str(e),
                    "completed_at": datetime.now().isoformat()
                }

        task = asyncio.create_task(wrapped_task())
        self._tasks[task_id] = task
        self._results[task_id] = {
            "status": "running",
            "agent": agent_name,
            "started_at": datetime.now().isoformat()
        }

        return task_id

    def get_status(self, task_id: str) -> dict:
        """태스크 상태 조회"""
        if task_id not in self._results:
            return {"status": "not_found", "task_id": task_id}
        return self._results[task_id]

    def get_all_status(self) -> dict[str, dict]:
        """모든 태스크 상태 조회"""
        return {
            task_id: {
                "status": info["status"],
                "agent": info["agent"],
                "started_at": info.get("started_at"),
                "completed_at": info.get("completed_at")
            }
            for task_id, info in self._results.items()
        }

    async def wait_for_task(self, task_id: str, timeout: float = None) -> dict:
        """특정 태스크 완료 대기"""
        if task_id not in self._tasks:
            return self.get_status(task_id)

        task = self._tasks[task_id]
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            return {"status": "timeout", "task_id": task_id}

        return self._results[task_id]

    async def wait_for_all(self, task_ids: list[str] = None, timeout: float = None) -> dict[str, dict]:
        """여러 태스크 완료 대기"""
        if task_ids is None:
            task_ids = list(self._tasks.keys())

        tasks_to_wait = [self._tasks[tid] for tid in task_ids if tid in self._tasks]

        if tasks_to_wait:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks_to_wait, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                pass

        return {tid: self._results.get(tid, {"status": "not_found"}) for tid in task_ids}

    def cleanup_completed(self) -> int:
        """완료된 태스크 정리"""
        completed = [
            tid for tid, info in self._results.items()
            if info["status"] in ("completed", "failed")
        ]
        for tid in completed:
            self._tasks.pop(tid, None)
            self._results.pop(tid, None)
        return len(completed)


# Global task manager
task_manager = TaskManager()


# ============================================
# History 관리 클래스
# ============================================

class HistoryManager:
    """작업 히스토리를 관리하는 클래스"""

    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.getcwd()
        self.history_dir = os.path.join(self.project_root, HISTORY_DIR_NAME)

    def ensure_history_dir(self) -> str:
        """history 폴더 생성"""
        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)
        return self.history_dir

    def get_history_files(self) -> list[str]:
        """모든 HISTORY_*.md 파일 목록 (정렬됨)"""
        pattern = os.path.join(self.history_dir, "HISTORY_*.md")
        files = glob.glob(pattern)
        # 숫자 기준 정렬
        files.sort(key=lambda x: int(os.path.basename(x).replace("HISTORY_", "").replace(".md", "").split("_")[0]) if os.path.basename(x).replace("HISTORY_", "").replace(".md", "").replace("_COMPACT", "").isdigit() else 0)
        return files

    def get_next_history_number(self) -> int:
        """다음 히스토리 파일 번호"""
        files = self.get_history_files()
        if not files:
            return 1
        # 마지막 파일에서 번호 추출
        last_file = os.path.basename(files[-1])
        try:
            num = int(last_file.replace("HISTORY_", "").replace(".md", "").split("_")[0])
            return num + 1
        except ValueError:
            return len(files) + 1

    def save_to_history(self, agent_name: str, request: str, response: str, metadata: dict = None) -> str:
        """작업 결과를 히스토리에 저장"""
        self.ensure_history_dir()

        # Compaction 확인
        files = self.get_history_files()
        if len(files) >= MAX_HISTORY_FILES:
            self.compact_history()

        # 새 히스토리 파일 생성
        next_num = self.get_next_history_number()
        filename = f"HISTORY_{next_num}.md"
        filepath = os.path.join(self.history_dir, filename)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        content = f"""# History #{next_num}

**시간**: {timestamp}
**에이전트**: {agent_name}

## 요청
{request}

## 응답
{response}
"""

        if metadata:
            content += f"\n## 메타데이터\n```json\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n```\n"

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return filepath

    def compact_history(self) -> str:
        """오래된 히스토리를 묶어서 저장"""
        files = self.get_history_files()
        if len(files) < MAX_HISTORY_FILES:
            return None

        # 앞의 파일들을 묶음
        files_to_compact = files[:len(files) - COMPACT_INTO]
        if not files_to_compact:
            return None

        # Compact 파일 생성
        compact_num = self.get_next_history_number()
        compact_filename = f"HISTORY_{compact_num}_COMPACT.md"
        compact_filepath = os.path.join(self.history_dir, compact_filename)

        compact_content = f"""# History Compact (#{compact_num})

**생성 시간**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**포함된 히스토리**: {len(files_to_compact)}개

---

"""

        for f in files_to_compact:
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
                compact_content += f"\n{content}\n---\n"

        with open(compact_filepath, 'w', encoding='utf-8') as f:
            f.write(compact_content)

        # 묶인 파일들 삭제
        for f in files_to_compact:
            os.remove(f)

        return compact_filepath

    def get_recent_history(self, count: int = 5) -> str:
        """최근 히스토리 요약"""
        files = self.get_history_files()
        recent = files[-count:] if len(files) >= count else files

        if not recent:
            return "히스토리가 없습니다."

        summary = f"## 최근 히스토리 ({len(recent)}개)\n\n"
        for f in reversed(recent):
            filename = os.path.basename(f)
            with open(f, 'r', encoding='utf-8') as file:
                lines = file.readlines()[:10]  # 첫 10줄만
                summary += f"### {filename}\n{''.join(lines)}\n...\n\n"

        return summary


# Global history manager (프로젝트 루트는 나중에 설정)
history_manager: HistoryManager = None


def get_history_manager() -> HistoryManager:
    """HistoryManager 인스턴스 반환 (lazy init)"""
    global history_manager
    if history_manager is None:
        history_manager = HistoryManager()
    return history_manager


def set_project_root(root: str):
    """프로젝트 루트 설정"""
    global history_manager
    history_manager = HistoryManager(root)

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

async def run_codex(prompt: str) -> str:
    """Codex CLI를 통해 GPT에게 질문 (OAuth 인증)

    Codex CLI 0.79.0+ 사용
    - ChatGPT 계정 로그인 시 자동으로 gpt-5.2-codex 모델 사용
    - --full-auto: 자동 실행 모드 (샌드박스 내에서 승인 없이 실행)
    - -o: 마지막 응답을 파일로 저장

    주의: ChatGPT 계정 인증 시 --model 옵션으로 모델 지정 불가
    """
    if not has_codex_cli():
        raise RuntimeError("Codex CLI가 설치되어 있지 않습니다. 'npm install -g @openai/codex'로 설치하세요.")

    import tempfile

    # 임시 파일로 출력 받기
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
        output_file = tmp.name

    try:
        # ChatGPT 계정 인증 시 모델 지정 불가 - 자동으로 gpt-5.2-codex 사용
        process = await asyncio.create_subprocess_exec(
            CODEX_PATH, "exec", prompt,
            "--full-auto",
            "-o", output_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            stdout_msg = stdout.decode().strip()
            combined_msg = f"{error_msg}\n{stdout_msg}".strip()

            if "not logged in" in combined_msg.lower() or "auth" in combined_msg.lower() or "login" in combined_msg.lower():
                raise RuntimeError(
                    "Codex CLI에 로그인이 필요합니다.\n"
                    "터미널에서 'codex' 명령어를 실행하고 ChatGPT 계정으로 로그인하세요."
                )
            raise RuntimeError(f"Codex CLI 오류: {combined_msg}")

        # 출력 파일에서 결과 읽기
        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8') as f:
                result = f.read().strip()
            if result:
                return result

        # 파일이 비어있으면 stdout 반환
        return stdout.decode().strip()

    finally:
        # 임시 파일 정리
        if os.path.exists(output_file):
            os.remove(output_file)


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

async def run_gemini(prompt: str, image_path: str = None) -> str:
    """Gemini CLI를 통해 Gemini에게 질문 (OAuth 인증, 이미지 지원)

    이미지를 사용할 때는 @image_path 형식으로 프롬프트에 추가합니다.
    """
    if not has_gemini_cli():
        raise RuntimeError("Gemini CLI가 설치되어 있지 않습니다. 'npm install -g @google/gemini-cli'로 설치하세요.")

    # 이미지가 있으면 프롬프트에 @path 형식으로 추가
    if image_path and os.path.exists(image_path):
        full_prompt = f"{prompt}\n\n이미지: @{image_path}"
    else:
        full_prompt = prompt

    process = await asyncio.create_subprocess_exec(
        GEMINI_PATH, full_prompt,
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

async def run_gpt(prompt: str, model: str = "gpt-4o", system_prompt: str = "", use_api: bool = False) -> tuple[str, str]:
    """GPT 실행 (CLI 우선)

    - Codex CLI (ChatGPT 계정): 자동으로 gpt-5.2-codex 사용 (모델 지정 불가)
    - OpenAI API: model 파라미터로 지정된 모델 사용
    """
    if use_api or (not has_codex_cli() and has_openai_api_key()):
        result = await run_openai_api(prompt, model, system_prompt)
        return result, f"OpenAI API ({model})"
    elif has_codex_cli():
        # Codex CLI는 ChatGPT 계정 인증 시 자동으로 gpt-5.2-codex 사용
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        result = await run_codex(full_prompt)
        return result, "Codex CLI (gpt-5.2-codex)"
    elif has_openai_api_key():
        result = await run_openai_api(prompt, model, system_prompt)
        return result, f"OpenAI API ({model})"
    else:
        raise RuntimeError("GPT 사용 불가: Codex CLI 로그인 또는 API 키 설정 필요")


async def run_gemini_agent(prompt: str, model: str = "gemini-3", use_api: bool = False, image_path: str = None) -> tuple[str, str]:
    """Gemini 실행 (CLI 우선, 이미지도 CLI로 지원) - 기본 모델: Gemini 3

    Gemini CLI는 @./path/to/image.png 형식으로 이미지를 지원합니다.
    """
    if use_api or (not has_gemini_cli() and has_gemini_api_key()):
        if image_path:
            result = await run_gemini_api(prompt, model, image_path=image_path)
            return result, f"Gemini API ({model}) + Image"
        result = await run_gemini_api(prompt, model)
        return result, f"Gemini API ({model})"
    elif has_gemini_cli():
        # CLI로 이미지 지원 (@ 형식)
        result = await run_gemini(prompt, image_path=image_path)
        method = "Gemini CLI (gemini-3)"
        if image_path:
            method += " + Image"
        return result, method
    elif has_gemini_api_key():
        if image_path:
            result = await run_gemini_api(prompt, model, image_path=image_path)
            return result, f"Gemini API ({model}) + Image"
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
1. Codex CLI (ChatGPT 계정 로그인) - API 키 불필요, 자동으로 gpt-5.2-codex 사용
2. OpenAI API 키 - .env에 OPENAI_API_KEY 설정, model 파라미터로 모델 선택 가능

Codex CLI 로그인: 터미널에서 'codex' 실행 후 ChatGPT 계정으로 로그인""",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "GPT에게 보낼 질문/프롬프트"
                    },
                    "model": {
                        "type": "string",
                        "description": "API 사용 시 모델 선택 (CLI 사용 시 무시됨, 자동으로 gpt-5.2-codex 사용)",
                        "enum": ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini"],
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
            name="oracle",
            description="""🔮 Oracle - 고급 추론 에이전트

복잡한 문제 해결, 아키텍처 설계, 알고리즘 설계 등 깊은 추론이 필요한 작업에 사용합니다.
Codex CLI 사용 시 자동으로 gpt-5.2-codex 모델로 step-by-step 분석합니다.

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

Gemini CLI의 @path 기능을 사용하여 이미지를 분석합니다.
API 키 없이 CLI 로그인만으로 사용 가능합니다.

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
        ),

        # ========== History 관리 ==========
        Tool(
            name="set_project_root",
            description="""프로젝트 루트 경로를 설정합니다.

히스토리 파일이 저장될 위치를 지정합니다.
설정하지 않으면 현재 작업 디렉토리가 사용됩니다.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "프로젝트 루트 경로 (절대 경로)"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="get_history",
            description="""최근 작업 히스토리를 조회합니다.

history/ 폴더에 저장된 HISTORY_*.md 파일들을 조회합니다.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "조회할 히스토리 개수 (기본값: 5)",
                        "default": 5
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="compact_history",
            description="""히스토리 파일을 압축합니다.

오래된 히스토리 파일들을 하나의 COMPACT 파일로 묶습니다.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),

        # ========== 비동기 태스크 관리 ==========
        Tool(
            name="dispatch_agent",
            description="""🚀 에이전트를 백그라운드로 실행하고 즉시 task_id를 반환합니다.

Claude가 여러 sub agent를 병렬로 실행하고 다른 작업을 계속할 수 있습니다.
결과는 나중에 get_task_result로 수집합니다.

사용 예시:
1. dispatch_agent로 Oracle, Frontend Designer 동시 실행
2. Claude는 다른 작업 수행 (코드 탐색, 파일 읽기 등)
3. get_task_result로 결과 수집

지원 에이전트: oracle, frontend_designer, document_writer, ask_gpt, ask_gemini""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "description": "실행할 에이전트",
                        "enum": ["oracle", "frontend_designer", "document_writer", "ask_gpt", "ask_gemini"]
                    },
                    "args": {
                        "type": "object",
                        "description": "에이전트에 전달할 인자 (각 에이전트의 inputSchema 참고)"
                    }
                },
                "required": ["agent", "args"]
            }
        ),
        Tool(
            name="get_task_result",
            description="""📥 백그라운드 태스크의 결과를 가져옵니다.

task_id로 특정 태스크의 결과를 조회하거나,
wait=true로 완료될 때까지 대기할 수 있습니다.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "조회할 태스크 ID"
                    },
                    "wait": {
                        "type": "boolean",
                        "description": "완료될 때까지 대기할지 여부 (기본값: false)",
                        "default": False
                    },
                    "timeout": {
                        "type": "number",
                        "description": "대기 시 최대 대기 시간(초) (기본값: 60)",
                        "default": 60
                    }
                },
                "required": ["task_id"]
            }
        ),
        Tool(
            name="list_tasks",
            description="""📋 모든 백그라운드 태스크의 상태를 조회합니다.

실행 중, 완료, 실패한 태스크들의 목록과 상태를 보여줍니다.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="wait_all_tasks",
            description="""⏳ 지정된 태스크들이 모두 완료될 때까지 대기합니다.

task_ids를 지정하지 않으면 실행 중인 모든 태스크를 대기합니다.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "대기할 태스크 ID 목록 (비어있으면 전체 대기)"
                    },
                    "timeout": {
                        "type": "number",
                        "description": "최대 대기 시간(초) (기본값: 120)",
                        "default": 120
                    }
                },
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
        elif name == "set_project_root":
            return await _set_project_root(arguments)
        elif name == "get_history":
            return await _get_history(arguments)
        elif name == "compact_history":
            return await _compact_history()
        # 비동기 태스크 관리
        elif name == "dispatch_agent":
            return await _dispatch_agent(arguments)
        elif name == "get_task_result":
            return await _get_task_result(arguments)
        elif name == "list_tasks":
            return await _list_tasks()
        elif name == "wait_all_tasks":
            return await _wait_all_tasks(arguments)
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
    """Oracle - 고급 추론 에이전트

    Codex CLI 사용 시 자동으로 gpt-5.2-codex 사용
    """
    problem = args["problem"]
    context = args.get("context", "")

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

    result, method = await run_gpt(full_prompt, system_prompt=system_prompt)

    # 히스토리에 저장
    save_agent_history("Oracle", problem, result, {"model": method, "context": context[:200] if context else None})

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

    # 히스토리에 저장
    save_agent_history("Frontend Designer", request, result, {"framework": framework, "styling": styling})

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

    # 히스토리에 저장
    save_agent_history("Document Writer", request, result, {"doc_type": doc_type, "language": language})

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

    # 히스토리에 저장
    save_agent_history("Multimodal Looker", request, result, {"task_type": task_type, "image_path": image_path})

    return [TextContent(
        type="text",
        text=f"## 👁️ Multimodal Looker 결과\n**방식**: {method}\n**작업**: {task_type}\n\n---\n\n{result}"
    )]


async def _compare_models(args: dict) -> list[TextContent]:
    """두 모델 비교"""
    prompt = args["prompt"]

    # Codex CLI는 자동으로 gpt-5.2-codex 사용, Gemini CLI는 gemini-3 사용
    gpt_task = run_gpt(prompt)
    gemini_task = run_gemini_agent(prompt)

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
        status_lines.append("   → 이미지 분석(Multimodal)도 CLI로 사용 가능")
    else:
        status_lines.append("❌ Gemini CLI 미설치")
        status_lines.append("   → 'npm install -g @google/gemini-cli'로 설치")

    if has_gemini_api_key():
        status_lines.append("✅ GEMINI_API_KEY 설정됨 (선택사항)")
    else:
        status_lines.append("⚪ GEMINI_API_KEY 미설정 (선택사항, CLI 우선)")

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
**사용 가능한 에이전트**: Frontend Designer, Document Writer, Multimodal Looker, ask_gemini

💡 **이미지 분석(Multimodal)도 CLI로 사용 가능!**
   Gemini CLI는 `@./path/to/image.png` 형식으로 이미지를 지원합니다.

---

## 참고

- 한번 로그인하면 토큰이 저장되어 이후에는 자동으로 인증됩니다
- CLI 로그인과 API 키를 동시에 설정해도 됩니다 (CLI 우선)
"""
    return [TextContent(type="text", text=guide)]


# ============================================
# History 관련 도구 구현
# ============================================

async def _set_project_root(args: dict) -> list[TextContent]:
    """프로젝트 루트 설정"""
    path = args["path"]

    if not os.path.isabs(path):
        return [TextContent(type="text", text=f"❌ 절대 경로를 입력해주세요: {path}")]

    if not os.path.exists(path):
        return [TextContent(type="text", text=f"❌ 경로가 존재하지 않습니다: {path}")]

    set_project_root(path)
    hm = get_history_manager()
    hm.ensure_history_dir()

    return [TextContent(
        type="text",
        text=f"✅ 프로젝트 루트 설정 완료\n\n경로: {path}\n히스토리 폴더: {hm.history_dir}"
    )]


async def _get_history(args: dict) -> list[TextContent]:
    """히스토리 조회"""
    count = args.get("count", 5)
    hm = get_history_manager()

    history = hm.get_recent_history(count)

    return [TextContent(
        type="text",
        text=f"# 작업 히스토리\n\n히스토리 폴더: {hm.history_dir}\n\n{history}"
    )]


async def _compact_history() -> list[TextContent]:
    """히스토리 압축"""
    hm = get_history_manager()

    result = hm.compact_history()

    if result:
        return [TextContent(
            type="text",
            text=f"✅ 히스토리 압축 완료\n\n생성된 파일: {result}"
        )]
    else:
        return [TextContent(
            type="text",
            text="ℹ️ 압축할 히스토리가 없습니다. (10개 미만)"
        )]


def save_agent_history(agent_name: str, request: str, response: str, metadata: dict = None):
    """에이전트 호출 결과를 히스토리에 저장 (동기 헬퍼)"""
    try:
        hm = get_history_manager()
        hm.save_to_history(agent_name, request, response, metadata)
    except Exception as e:
        # 히스토리 저장 실패는 무시 (메인 기능에 영향 주지 않음)
        pass


# ============================================
# 비동기 태스크 관리 도구 구현
# ============================================

async def _dispatch_agent(args: dict) -> list[TextContent]:
    """에이전트를 백그라운드로 실행"""
    agent = args["agent"]
    agent_args = args["args"]

    # 에이전트별 코루틴 생성
    agent_name_map = {
        "oracle": "Oracle",
        "frontend_designer": "Frontend Designer",
        "document_writer": "Document Writer",
        "ask_gpt": "GPT",
        "ask_gemini": "Gemini"
    }

    if agent not in agent_name_map:
        return [TextContent(
            type="text",
            text=f"❌ 지원하지 않는 에이전트: {agent}"
        )]

    # 에이전트별 코루틴 생성
    if agent == "oracle":
        coro = _run_oracle_async(agent_args)
    elif agent == "frontend_designer":
        coro = _run_frontend_designer_async(agent_args)
    elif agent == "document_writer":
        coro = _run_document_writer_async(agent_args)
    elif agent == "ask_gpt":
        coro = _run_gpt_async(agent_args)
    elif agent == "ask_gemini":
        coro = _run_gemini_async(agent_args)

    # 백그라운드로 시작
    task_id = await task_manager.start_task(agent_name_map[agent], coro)

    return [TextContent(
        type="text",
        text=f"🚀 **{agent_name_map[agent]}** 백그라운드 실행 시작\n\n**Task ID**: `{task_id}`\n\n결과 조회: `get_task_result(task_id=\"{task_id}\")`"
    )]


async def _get_task_result(args: dict) -> list[TextContent]:
    """태스크 결과 조회"""
    task_id = args["task_id"]
    wait = args.get("wait", False)
    timeout = args.get("timeout", 60)

    if wait:
        result = await task_manager.wait_for_task(task_id, timeout=timeout)
    else:
        result = task_manager.get_status(task_id)

    if result["status"] == "not_found":
        return [TextContent(
            type="text",
            text=f"❌ 태스크를 찾을 수 없습니다: {task_id}"
        )]

    if result["status"] == "running":
        return [TextContent(
            type="text",
            text=f"⏳ **{result['agent']}** 실행 중...\n\n**Task ID**: `{task_id}`\n**시작 시간**: {result['started_at']}\n\n`wait=true`로 대기하거나 나중에 다시 조회하세요."
        )]

    if result["status"] == "timeout":
        return [TextContent(
            type="text",
            text=f"⏰ 타임아웃: {timeout}초 내에 완료되지 않았습니다.\n\n나중에 다시 조회하세요."
        )]

    if result["status"] == "failed":
        return [TextContent(
            type="text",
            text=f"❌ **{result['agent']}** 실패\n\n**오류**: {result['error']}"
        )]

    # 완료된 경우
    agent_result = result["result"]
    duration = result.get("duration_seconds", 0)

    return [TextContent(
        type="text",
        text=f"✅ **{result['agent']}** 완료 ({duration:.1f}초)\n\n---\n\n{agent_result}"
    )]


async def _list_tasks() -> list[TextContent]:
    """모든 태스크 상태 조회"""
    all_status = task_manager.get_all_status()

    if not all_status:
        return [TextContent(
            type="text",
            text="📋 실행 중인 태스크가 없습니다."
        )]

    lines = ["# 📋 태스크 목록\n"]

    running = [(tid, info) for tid, info in all_status.items() if info["status"] == "running"]
    completed = [(tid, info) for tid, info in all_status.items() if info["status"] == "completed"]
    failed = [(tid, info) for tid, info in all_status.items() if info["status"] == "failed"]

    if running:
        lines.append(f"## ⏳ 실행 중 ({len(running)}개)")
        for tid, info in running:
            lines.append(f"- `{tid}` - {info['agent']} (시작: {info['started_at']})")
        lines.append("")

    if completed:
        lines.append(f"## ✅ 완료 ({len(completed)}개)")
        for tid, info in completed:
            lines.append(f"- `{tid}` - {info['agent']}")
        lines.append("")

    if failed:
        lines.append(f"## ❌ 실패 ({len(failed)}개)")
        for tid, info in failed:
            lines.append(f"- `{tid}` - {info['agent']}")

    return [TextContent(type="text", text="\n".join(lines))]


async def _wait_all_tasks(args: dict) -> list[TextContent]:
    """모든 태스크 대기"""
    task_ids = args.get("task_ids", [])
    timeout = args.get("timeout", 120)

    if not task_ids:
        # 실행 중인 모든 태스크
        all_status = task_manager.get_all_status()
        task_ids = [tid for tid, info in all_status.items() if info["status"] == "running"]

    if not task_ids:
        return [TextContent(
            type="text",
            text="📋 대기할 태스크가 없습니다."
        )]

    results = await task_manager.wait_for_all(task_ids, timeout=timeout)

    lines = [f"# ⏳ {len(task_ids)}개 태스크 대기 완료\n"]

    for tid, result in results.items():
        if result["status"] == "completed":
            lines.append(f"✅ `{tid}` - {result['agent']} 완료")
        elif result["status"] == "failed":
            lines.append(f"❌ `{tid}` - {result['agent']} 실패: {result.get('error', 'Unknown error')}")
        elif result["status"] == "running":
            lines.append(f"⏳ `{tid}` - {result['agent']} 아직 실행 중 (타임아웃)")
        else:
            lines.append(f"❓ `{tid}` - 상태: {result['status']}")

    lines.append("\n각 결과 상세 조회: `get_task_result(task_id=\"...\")`")

    return [TextContent(type="text", text="\n".join(lines))]


# 비동기 에이전트 실행 헬퍼 함수들
async def _run_oracle_async(args: dict) -> str:
    """Oracle 비동기 실행"""
    problem = args["problem"]
    context = args.get("context", "")

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

    result, method = await run_gpt(full_prompt, system_prompt=system_prompt)
    save_agent_history("Oracle", problem, result, {"model": method})
    return f"## 🔮 Oracle 분석 결과\n**모델**: {method}\n\n---\n\n{result}"


async def _run_frontend_designer_async(args: dict) -> str:
    """Frontend Designer 비동기 실행"""
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

Please generate clean, well-structured code following best practices for the specified stack."""

    result, method = await run_gemini_agent(prompt)
    save_agent_history("Frontend Designer", request, result, {"framework": framework, "styling": styling})
    return f"## 🎨 Frontend Designer 결과\n**방식**: {method}\n**Framework**: {framework} + {styling}\n\n---\n\n{result}"


async def _run_document_writer_async(args: dict) -> str:
    """Document Writer 비동기 실행"""
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

Please write professional documentation."""

    result, method = await run_gemini_agent(prompt)
    save_agent_history("Document Writer", request, result, {"doc_type": doc_type, "language": language})
    return f"## 📝 Document Writer 결과\n**방식**: {method}\n**문서 유형**: {doc_type_map.get(doc_type, doc_type)}\n\n---\n\n{result}"


async def _run_gpt_async(args: dict) -> str:
    """GPT 비동기 실행"""
    prompt = args["prompt"]
    model = args.get("model", "gpt-4o")
    use_api = args.get("use_api", False)

    result, method = await run_gpt(prompt, model, use_api=use_api)
    return f"## GPT 응답\n**방식**: {method}\n\n---\n\n{result}"


async def _run_gemini_async(args: dict) -> str:
    """Gemini 비동기 실행"""
    prompt = args["prompt"]
    model = args.get("model", "gemini-3")
    use_api = args.get("use_api", False)

    result, method = await run_gemini_agent(prompt, model, use_api=use_api)
    return f"## Gemini 응답\n**방식**: {method}\n\n---\n\n{result}"


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
