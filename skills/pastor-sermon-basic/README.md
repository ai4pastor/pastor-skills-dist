# pastor-sermon-basic (개발자·강사용 개요)

`pastor-sermon-import`의 **입문 경로**. 산출물은 같고 온보딩만 다르다.

## import 와의 차이

| | basic | import |
|---|---|---|
| 온보딩 질문 | **5개** (폴더 위치만) | 12개 (+ 프리셋 세부 6개) |
| 파일명 규칙 | `guess_naming.py` 로 추론 → 확인만 | 목사님이 지정 |
| 폴더 지정 | `suggest_folders.py` 후보에서 선택 | 경로 직접 입력 |
| 분류 목록 | 볼트 노트 자동 탐색 → 프리셋 → 미사용 | 3경로 + 축별 세부 선택 |
| 조각 충돌 | `skip` 고정 | `skip` / `merge` / `ask` |
| 검증 규칙 | 분류 쓰면 일괄 on | 항목별 on/off |
| 명령 | 1개 (`/pastor-sermon-basic`) | 2개 (setup + import) |
| 산출물 | **동일** | 동일 |

설정 파일 스키마가 같으므로 basic → import 이관은 재설정 없이 된다.

## 고유 파일

- `SKILL.md` · `INSTALL.md` · `README.md`
- `prompts/onboarding.md` — 5문항
- `scripts/suggest_folders.py` — 볼트 폴더·분류 노트 후보 탐색 (깊이 3 제한, 성경 노트 수만 개 볼트 고려)
- `scripts/guess_naming.py` — 파일명 날짜·대상 패턴 추론. **2회 이상 반복된 짧은 토큰만** 대상 표시로 인정한다(1회짜리는 제목 첫 단어일 확률이 높다)

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
