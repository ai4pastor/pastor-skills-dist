# pastor-sermon-basic (개발자·강사용 개요)

`pastor-sermon-import`의 **입문 경로**. 산출물은 같고 온보딩만 다르다.

## import 와의 차이

| | basic | import |
|---|---|---|
| 온보딩 질문 | **7개** (어디서·어떻게 나눠·어디에) | 14개 (+ 형식·검증 세부) |
| 파일명 규칙 | `guess_naming.py` 로 추론 → 확인만 | 목사님이 지정 |
| 폴더 지정 | `suggest_folders.py` 후보에서 선택 | 후보 + 경로 직접 입력 |
| 설교 구분 | 3단 질문 (구분 → 원본 기준 → 노트 반영) | 같음 + 구분별 폴더 세부 지정 |
| 분류 목록 | 템플릿·900번대 자동 탐색 → 프리셋 → 미사용 | 3경로 + 축별 세부 선택 |
| 조각 충돌 | `skip` 고정 | `skip` / `merge` / `ask` |
| 검증 규칙 | 분류 쓰면 일괄 on | 항목별 on/off |
| 명령 | 1개 (`/pastor-sermon-basic`) | 2개 (setup + import) |
| 산출물 | **동일** | 동일 |

설정 파일 스키마가 같으므로 basic → import 이관은 재설정 없이 된다.

## 고유 파일

- `SKILL.md` · `INSTALL.md` · `README.md`
- `prompts/onboarding.md` — 7문항 순차형

탐색 스크립트(`find_sources.py`·`suggest_folders.py`·`guess_naming.py`)는 공유 파일이다.
두 스킬이 같은 판단을 해야 하므로 원본은 `pastor-sermon-import` 에 둔다.

## 공유 파일

나머지 스크립트·프롬프트·프리셋은 `pastor-sermon-import`에서 복사해 온다.
모노레포 규약상 스킬 폴더는 자급자족해야 하므로 심볼릭이 아니라 복사다.

```bash
python3 tools/sync_basic.py --check   # 차이 확인
python3 tools/sync_basic.py           # 반영
```

**공유 파일은 이 폴더에서 고치지 않는다.** `pastor-sermon-import`에서 고치고 sync 한다.

## 테스트

```bash
python3 tests/pastor-sermon-basic/run_smoke.sh
```
