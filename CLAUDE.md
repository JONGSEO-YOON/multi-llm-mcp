
## Multi-LLM Sub Agents

다음 MCP 도구들을 상황에 맞게 **자동으로** 사용하세요:

### 🔮 Oracle (GPT-5.2-codex) - `mcp__multi-llm__oracle`
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
**사용 시점**: 이미지/스크린샷 분석이 필요할 때
- UI 스크린샷에서 코드 생성
- 디자인 피드백 제공
- 에러 스크린샷 분석

---

## 🚀 병렬 실행 (Async Dispatch)

여러 에이전트를 **동시에 실행**하고 나중에 결과를 수집할 수 있습니다:

### `dispatch_agent` - 백그라운드 실행
```
dispatch_agent(agent="oracle", args={"problem": "..."})
→ task_id 즉시 반환, 백그라운드 실행
```

### `get_task_result` - 결과 수집
```
get_task_result(task_id="oracle_123456_1", wait=true)
→ 완료 대기 후 결과 반환
```

### `list_tasks` - 태스크 목록
```
list_tasks()
→ 실행 중/완료/실패 태스크 목록
```

### `wait_all_tasks` - 모두 대기
```
wait_all_tasks(timeout=120)
→ 모든 실행 중인 태스크 완료 대기
```

### 사용 예시
```
1. dispatch_agent(agent="oracle", args={...})      → task_1
2. dispatch_agent(agent="frontend_designer", args={...}) → task_2
3. Claude는 다른 작업 수행 (파일 읽기, 코드 탐색 등)
4. wait_all_tasks() 또는 get_task_result로 결과 수집
```

---

## 사용 규칙
1. 위 상황에 해당하면 **자동으로** 해당 도구를 사용
2. 일반적인 코드 탐색, 검색, 편집은 Claude가 직접 수행
3. 도구 사용 전 사용자에게 물어볼 필요 없음
4. **복잡한 작업은 dispatch_agent로 병렬 실행** 권장

