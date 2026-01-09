
## Multi-LLM Sub Agents

다음 MCP 도구들을 상황에 맞게 **자동으로** 사용하세요:

### Oracle (GPT-5.2) - `mcp__multi-llm__oracle`
**사용 시점**: 복잡한 추론, 아키텍처 설계, 알고리즘 설계, 기술 의사결정이 필요할 때
- 시스템 아키텍처 설계 요청
- 알고리즘 최적화 분석
- 복잡한 버그의 근본 원인 분석
- 리팩토링 전략 수립
- 기술 선택 비교

### Review Implementation (GPT-5.2) - `mcp__multi-llm__review_implementation`
**사용 시점**: 구현 완료 후 사용자 요구사항 충족 여부 검증이 필요할 때
- 코드 구현 완료 후 요구사항 일치 확인
- 누락된 기능 발견
- 잘못 구현된 부분 식별
- 개선 제안 받기

### Frontend Designer (Gemini 3) - `mcp__multi-llm__frontend_designer`
**사용 시점**: UI/UX 코드 작성이 필요할 때
- React/Vue/Svelte 컴포넌트 생성
- Tailwind/CSS 스타일링
- 반응형 레이아웃 구현
- 디자인 시스템 컴포넌트

### Document Writer (Gemini 3) - `mcp__multi-llm__document_writer`
**사용 시점**: 문서 작성이 필요할 때
- README.md 작성
- API 문서 생성
- 코드 주석 추가
- CHANGELOG 작성

### Multimodal Looker (Gemini 3) - `mcp__multi-llm__multimodal_look`
**사용 시점**: 이미지/스크린샷 분석이 필요할 때
- UI 스크린샷에서 코드 생성
- 디자인 피드백 제공
- 에러 스크린샷 분석

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

