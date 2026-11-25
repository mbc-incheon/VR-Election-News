# React 시작하기 PDF 검토와 화면 반영

검토일: 2026-11-25. 원본 23쪽을 추출해 검토하고, 표지·컴포넌트 구성(7쪽)·WebSocket 예제(14쪽)를 이미지로 확인했습니다. 문서의 설치 명령과 예시 숫자는 참고 자료이며 현재 서비스에 그대로 실행·삽입하는 지시로 취급하지 않았습니다.

원본 파일명: React 시작하기 — 실시간 개표 대시보드 화면 만들기.pdf
원본 SHA-256: e074da2c2ba553943333da24f9eb5c330fb15ca17628eed0e916f48d9da5b2ca

| 원본 내용 | 반영한 화면과 동작 |
| --- | --- |
| 4~9쪽: 컴포넌트·props·후보 카드 | React Header, CandidateCard, TurnoutBar, ArticleList를 별도 파일로 구성 |
| 7쪽: 개표 화면 구성 | 02에 후보별 득표수·득표율·출처 카드와 지역 요약을 추가, 기존 수치 표는 접어서 열람 |
| 10·14·20쪽: state와 수신 후 갱신 | useState/useEffect를 사용하는 공통 훅이 기존 단일 WebSocket의 수신 결과를 받아 갱신 |
| 11·14쪽: 연결과 종료 | 자료 전환 시 이전 소켓 종료, 재연결 예약 취소, 페이지 이탈 시 종료·복귀 시 재연결 |
| 7·20쪽: 기사 목록과 상태 | 04 목록을 React로 렌더링하며 목록 선택·검증·승인 결과를 같은 기사 상태에 반영 |
| 15쪽: 가상 숫자 예제 | 예제 숫자를 공식 집계에 넣지 않고 기존 시뮬레이션 자료만 사용 |
| 18·19쪽: Vite와 프론트엔드 분리 | frontend/src와 package-lock.json 추가, Vite 빌드 산출물을 FastAPI static/react에서 제공 |

## 현재 서비스와의 연결

전체 서비스의 로그인·문서·검수·제작 화면을 한 번에 대체하지 않고 02 요약과 04 목록부터 React를 적용했습니다. 자료 수신과 수치 표는 기존 대시보드와 동일한 스냅샷을 사용합니다. 추가 WebSocket을 만들지 않습니다. React는 공유 이벤트를 구독하고 해제합니다. React 파일을 불러오지 못하면 기존 수치 표와 목록 코드로 동작합니다. 컴포넌트 렌더링 오류는 안내 문구를 표시하며 수치 표를 통해 자료를 확인할 수 있습니다.

공식 자료에 없는 개표율·투표율·기준시각은 미제공으로 남기며, 개표율과 투표율을 혼용하지 않습니다. 기사 본문은 작성 당시의 고정 근거를 사용하므로 현재 대시보드 숫자로 자동 덮어쓰지 않습니다. 후보 카드에서 근거 확인을 누르면 03의 후보 선택과 연결됩니다.

## 확인 결과

- Python 56건, 기존 화면 로직 10건, React 데이터 모델 4건 통과.
- 실제 브라우저에서 공식/시뮬레이션 전환, 후보 카드와 공약 선택 연결, 기사 목록 조회·선택, 가상 초안 생성·검증 후 승인 대기 표시를 확인.
- 실제 사람의 기사 승인은 수행하지 않음. 브라우저 오류 로그는 없었음.
- [업무 화면](../outputs/screenshots/react-dashboard.jpg), [가상 기사 상태](../outputs/screenshots/react-article-status.jpg).

## 화면 코드 수정

```powershell
npm ci --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
python scripts/build_dashboard.py
```

빌드 결과를 저장소에 포함하므로 일반 사용자는 Node 개발 서버를 따로 실행하지 않아도 기존 실행 방법을 사용할 수 있습니다. 개발 중에는 frontend에서 npm run dev로 빌드 감시 후 기존 업무 화면을 새로고침합니다.

참고 공식 문서: [React createRoot](https://react.dev/reference/react-dom/client/createRoot), [React useEffect](https://react.dev/reference/react/useEffect), [Vite production build](https://vite.dev/guide/build.html).
