# 개표 화면 React 컴포넌트

첨부 React 학습 자료의 컴포넌트·props·state·WebSocket 흐름을 기존 FastAPI 업무 화면에 단계적으로 적용합니다. 기존 서비스의 02 요약과 04 기사 목록을 React로 표시합니다.

- src/components: Header, CandidateCard, TurnoutBar, ArticleList
- src/hooks/useNewsroom.js: 기존 단일 스트림의 상태 구독과 해제
- src/model.js: 원본 결측값·지역별 집계·안전한 출처 링크
- vite.config.js: FastAPI static/react로 빌드, 외부 CDN 없이 실행

루트에서 npm ci --prefix frontend, npm test --prefix frontend, npm run build --prefix frontend를 실행합니다. 화면 HTML 수정 시 python scripts/build_dashboard.py도 실행하세요. 최종 화면은 기존 FastAPI 서버의 /에서 열립니다. npm run dev는 빌드 감시이며 별도 포트의 개발 웹 서버가 아닙니다.

[검토·적용 기록](../docs/react-dashboard-review.md)을 참고하세요.
