# a4p-pastoral-visit 플러그인 설치 (BRAT)

1. Obsidian → 설정 → 커뮤니티 플러그인 → 탐색 → **BRAT** 설치·활성화.
2. BRAT 설정 → `Add a beta plugin for testing` → 주소 입력:

```text
ai4pastor/a4p-pastoral-visit
```

3. 커뮤니티 플러그인 목록에서 **a4p-pastoral-visit** 를 켠다.
4. 플러그인 설정 → **폴더 경로** 에 두 값을 넣는다 (이 스킬의 `verify_visits.py` 가 마지막에 그대로 찍어 준다):
   - 성도 노트 폴더 — 예: `400. Education & Ministry/460. 성도`
   - 심방일지 폴더 — 예: `400. Education & Ministry/460. 성도/심방일지`
   입력란을 클릭하면 폴더 목록이 뜨고, 옆의 **[검증]** 을 누르면 폴더가 있는지·노트가 몇 개 잡히는지 보여 준다.
5. 왼쪽 리본의 심방 아이콘(또는 명령 팔레트 "심방 패널 열기")으로 대시보드를 연다.

대시보드 카드: 후속조치 미완 · 심방 필요 · 장기 미심방(기본 6개월) · 생일(14일) · 새등록 성도(90일, 심방 전) · 미반영 일지 · 진행 중인 기도제목 · 최근 심방.
심방일지를 쓴 뒤 **반영** 버튼을 누르면 미리보기(diff) 뒤에 성도 노트에 기록 줄과 임베드가 붙는다.

업데이트: BRAT 설정의 `Check for updates` 또는 Obsidian 재시작 시 자동.
