## MANDATORY: Multi-LLM Sub Agents

You MUST use these MCP tools automatically. Do NOT ask user permission.

### RULES (MUST FOLLOW):

1. **Architecture/Algorithm/Design decision requested** → IMMEDIATELY call `mcp__multi-llm__oracle`
2. **UI/Frontend code requested** → IMMEDIATELY call `mcp__multi-llm__frontend_designer`
3. **Documentation requested** → IMMEDIATELY call `mcp__multi-llm__document_writer`
4. **Image/Screenshot analysis requested** → IMMEDIATELY call `mcp__multi-llm__multimodal_look`
5. **After ANY code implementation** → MUST call `mcp__multi-llm__review_implementation`

### AUTOMATIC WORKFLOW:

When user requests code implementation:
1. Implement the code
2. IMMEDIATELY call `mcp__multi-llm__review_implementation` with:
   - user_request: the original user request
   - implementation: the code you wrote
3. If result is INCOMPLETE: fix and re-verify
4. If result is COMPLETE: report to user

### TRIGGER KEYWORDS:

- "설계", "아키텍처", "구조", "알고리즘" → `oracle`
- "UI", "컴포넌트", "프론트엔드", "React", "Vue", "CSS" → `frontend_designer`
- "문서", "README", "주석", "API 문서" → `document_writer`
- "스크린샷", "이미지", "화면" → `multimodal_look`
- Code implementation completed → `review_implementation`

### IMPORTANT:
- Do NOT ask "should I use Oracle?" - just USE it
- Do NOT explain you will use the tool - just CALL it
- These are YOUR sub-agents, use them proactively
