# Onboarding Prompt (basic)

목표: **설교를 어디서 가져와, 어떻게 나눠서, 어디에 넣을지**를 순서대로 여쭤보고
설정을 완성한다. **질문은 7개다.**

## 진행 원칙

- 한 번에 한 질문만 한다. 답을 받으면 그 자리에서 확인하고 다음으로 넘어간다.
- **빈칸을 타이핑하게 두지 않는다.** 컴퓨터와 볼트를 먼저 훑어 후보를 번호로 제시한다.
- 목사님이 "잘 모르겠다"고 하면 가장 그럴듯한 후보를 권하고 이유를 한 줄로 말한다.
- 파일명 규칙·저장 형식·검증 규칙은 **묻지 않는다.** 추론하고 확인만 받는다.
- 설정 파일을 쓰기 전 미리보기를 보여주고 승인을 받는다.
- 목사님의 원고·노트·템플릿은 **읽기만 한다.** 하나도 고치지 않는다.

---

## 질문 1. 옵시디언 볼트가 어디에 있나요?

먼저 찾아본다. 묻기 전에 후보를 만든다.

```bash
python3 scripts/find_sources.py --vaults
```

```text
옵시디언 볼트를 찾았습니다.

  1) {vaults[0].path}        (노트 {notes}개, {where})
  2) {vaults[1].path}        (노트 {notes}개, {where})
  3) 직접 입력하겠습니다

어느 것이 목사님 볼트인가요?
```

못 찾으면 경로를 여쭙고, 확인 방법을 한 줄 덧붙인다 —
"옵시디언에서 볼트 이름을 오른쪽 클릭 → `Reveal in Finder`(윈도우: `탐색기에서 보기`)".

경로를 받으면 곧바로 볼트 구조를 읽는다:

```bash
python3 scripts/suggest_folders.py "{볼트 경로}"
```

이 한 번의 실행으로 질문 6·7의 폴더 후보와 **분류 정본 노트·설교 템플릿**까지 확보된다.
`sermon_templates` 가 잡히면 목사님이 이미 쓰는 frontmatter 필드 이름·순서를 알 수 있으므로
그 순서에 맞춰 노트를 만든다.

---

## 질문 2. 설교 원고를 어디서 가져올까요?

**이 질문은 항상 한다.** 볼트 안에 원고가 있다고 가정하지 않는다.

```bash
python3 scripts/find_sources.py
```

```text
설교 원고가 있을 만한 폴더를 찾았습니다.
(볼트 밖이어도 됩니다 — 구글 드라이브·원드라이브·iCloud·문서 폴더 어디든 괜찮습니다.
 원본은 읽기만 하고 고치지 않습니다.)

  1) {path}   [{where}]  문서 {documents}개 ({by_suffix})  최근 {latest_modified}
  2) {path}   [{where}]  문서 {documents}개 ({by_suffix})  최근 {latest_modified}
  3) 직접 입력하겠습니다
  4) 여러 폴더에 나뉘어 있습니다 (모두 알려 주세요)

어디서 가져올까요?
```

- `where` 가 클라우드(구글 드라이브·원드라이브·드롭박스·iCloud)면 그 사실을 그대로 보여준다.
- 후보가 없거나 `truncated` 가 참이면 폴더를 여쭙고 `--root "{경로}"` 로 그 폴더만 다시 훑는다.
- 여러 폴더면 `input.sermon_sources` 에 모두 넣는다(배열이다).

### 질문 2-1. 형식 확인과 도구 준비 (질문이 아니라 확인)

```bash
python3 scripts/scan_inputs.py "{설교 폴더}"
```

보고할 것과 처리 방법:

| 출력 | 목사님께 할 말 |
|---|---|
| `by_suffix` | "워드 {n}개 · 한글 {n}개 · PDF {n}개를 찾았습니다" |
| `skipped[].note` | 건너뛴 이유를 그대로 전한다 (구글 링크 파일·워드 잠금 파일·0바이트 등) |
| `ask_install` | **그 문구로 한 번 여쭙고** 승인 뒤 아래를 실행한다 |
| `ask_undeclared` | 설정에 없는 형식이 있을 때 함께 가져올지 여쭙고 `input.file_types` 를 늘린다 |

```bash
python3 scripts/ensure_tools.py --install {형식목록}
```

- 설치는 **스킬 전용 폴더**(`<설정 홈>/tools/pylibs`)에만 한다. 목사님 컴퓨터의 다른
  파이썬 설정은 건드리지 않는다.
- 설치가 실패하면 `manual` 안내(한글에서 `.txt` 또는 `.hwpx` 로 저장 등)를 전하고
  **여기서 멈추지 않는다.** 읽을 수 있는 파일부터 진행한다.
- `.gdoc` 은 실제 문서가 아니라 링크다 — 드라이브에서 `다운로드 → Word(.docx)` 를 안내한다.
- 나중에 `extract_text.py` 가 `scanned_pdf` 경고를 내면 그 설교는 스캔 이미지다.
  같은 설교의 원고 파일(`.docx`/`.hwp`/`.txt`)이 있는지 여쭤본다.

---

## 질문 3. 설교를 어떻게 나누고 계신가요? (세 단계)

목회 현장은 대예배·수요기도회·새벽기도회가 대부분이다. 부서 설교를 전제하지 않는다.

```bash
python3 scripts/guess_naming.py "{설교 폴더}"
```

### 3-1. 어떤 설교를 정리하시나요?

`sermon_kinds_detected` 가 있으면 **그것부터** 보여준다.

```text
파일과 폴더를 보니 이런 설교로 나뉘어 있습니다.

  {sermon_kinds_detected 를 번호로}

맞습니까? 빠진 것이 있으면 알려 주세요. (여러 개 고르실 수 있습니다)
```

못 찾았으면 흔한 구분을 제시하고 고르게 한다. 목록에 없으면 직접 받는다.

```text
  1) 주일 대예배        2) 주일 오후(저녁)예배   3) 수요기도회
  4) 새벽기도회         5) 금요기도회(철야)      6) 특별집회·부흥회
  7) 청년부             8) 청소년부(중고등부)     9) 어린이부(유년·유치부)
 10) 심방·경조사        11) 성경공부·강의        12) 구분하지 않겠습니다
```

12번이면 3-2·3-3을 건너뛰고 `sermon_kinds.enabled: false` 로 둔다.

### 3-2. 원본에서 이 구분이 어떻게 나뉘어 있나요?

`sermon_kind_hits` 와 `samples` 를 표로 보여주고 **확인만** 받는다.

```text
이렇게 읽었습니다.

  폴더로 나뉜 것        {폴더 → 구분}
  파일명 표시로 나뉜 것  {표시 → 구분}

  {samples 를 표로: 파일명 → 날짜 / 구분 표시 / 제목}

이렇게 읽으면 될까요?
```

- 틀린 항목만 고친다. 맞으면 `suggested` 의 `naming.*` 와 `sermon_kinds.*` 를 그대로 넣는다.
- 구분을 알 수 없는 파일이 있으면 그 목록을 보여주고, 구분 없이 둘지 여쭤본다.
- `date_ratio` 가 0.5 미만이면 "날짜가 없는 파일이 많습니다 — 노트 이름에서 날짜를 빼고
  제목만 쓸까요?"를 함께 여쭤본다.

### 3-3. 노트에서는 어떻게 나눌까요?

```text
  1) 노트 속성으로만 표시합니다 (폴더는 하나)
  2) 파일명에 표시합니다  (260208_주일대예배_은혜의 복음_엡2_8.md)
  3) 구분마다 폴더를 나눕니다
  4) 1 + 2  (권장)
  5) 구분하지 않습니다
```

고른 것에 따라 설정이 이렇게 정해진다. 다른 것은 묻지 않는다.

| 선택 | 설정 |
|---|---|
| 1 | `sermon_kinds.frontmatter_key: "설교구분"` |
| 2 | `naming.main_note_pattern` 에 `{kind}` (짧은 표시를 쓰시면 `{target}`) |
| 3 | `sermon_kinds.folder_by_kind` — 구분별 폴더를 이어서 여쭤본다 |
| 4 | 1 + 2 를 함께 |
| 5 | `frontmatter_key: ""` · 패턴에 구분 없음 |

3번이면 질문 6에서 구분별 폴더를 한 번에 확인한다. 폴더가 없으면 만들 이름을 제안한다
(설교 폴더가 번호 체계면 그 체계에 맞춘다 — 예: `310. 새벽기도회`).

---

## 질문 4. 정리된 설교 노트를 볼트 어느 폴더에 넣을까요?

`suggest_folders.py` 의 `sermon_folders` 후보를 `path` (노트 `notes` 개) 형태로,
점수 높은 순으로 번호를 붙여 제시한다.

```text
볼트에서 설교 관련 폴더를 찾았습니다.

  1) {후보 1 path}        (노트 {notes}개)
  2) {후보 2 path}        (노트 {notes}개)
  3) 직접 입력하겠습니다
  4) 새 폴더를 만들어 주세요 (이름을 알려 주세요)

어디에 넣을까요?
```

노트 수가 가장 많은 후보를 먼저 권하고 이유를 한 줄로 말한다.
질문 3-3에서 3번(폴더 분리)을 고르셨으면 **구분마다** 폴더를 확인한다.

---

## 질문 5. 설교 조각(작은 메모)은 어느 폴더에 넣을까요?

`fragment_folders` 후보를 같은 방식으로 제시한다. 후보가 없으면 `설교조각`을 권하되,
질문 4에서 고른 설교 폴더가 번호 체계(`숫자. 이름`)를 쓰고 있으면 그 체계에 맞춘
이름을 함께 제안한다.

조각이 무엇인지 한 줄로 설명한다:

```text
설교 한 편을 논지·해석·예화·적용 단위로 나눈 작은 메모입니다.
나중에 다른 설교를 준비하실 때 이 조각들이 검색·재사용됩니다.
```

---

## 질문 6. 분류(WORD)를 쓰시나요?

`suggest_folders.py` 가 이미 `word_notes`(분류 정본 후보)와 `sermon_templates` 를
찾아 두었다. 비어 있으면 한 번 더 찾아본다 — 정본은 보통 템플릿 폴더나
900번대 세팅 폴더에 있다.

```bash
python3 scripts/find_word_template.py "{볼트 경로}"
```

```text
분류를 정리해 두신 노트를 찾았습니다.

  1) {word_notes[0].path}
     ({matched_axes 를 "World N개 · Outcome N개 · Route N개 · Doctrine N개" 로})
  2) 강의 표준 분류표를 쓰겠습니다
  3) 분류는 쓰지 않겠습니다

어느 것으로 할까요?
```

### 1번 — 목사님 분류표를 쓴다

```bash
python3 scripts/parse_word_source.py "{볼트}/{후보 경로}" --sermon-only
```

`sermon_subset` 만 확인한다. **설교 임포트에 분류 전체가 필요하지는 않다.**

```text
설교에 쓸 값만 골랐습니다.

  설교 분류(World)   {sermon_subset.world.values}
  활용 목적(Outcome) {sermon_subset.outcome.recommended}
  진행 단계(Route)   {sermon_subset.route.recommended}
  신학 주제(Doctrine) {sermon_subset.doctrine.count}개 전체를 후보로 둡니다

맞습니까?
```

그다음 `sermon_subset.ask` 의 문구를 **순서대로** 여쭤본다. 그중 Route 질문이 핵심이다 —
설교는 이미 설교하신 완성 원고이므로 `완료` 성격 값을 기본으로 권한다.
못 읽은 축이 있으면 `--explain` 으로 찾는 모양을 안내한다. **그 노트는 수정하지 않는다.**

### 2번 — 강의 표준 분류표

`data/word_preset.a4p.json` 을 읽어 허용 목록에 넣는다.
설교에 쓸 값은 `axes.world.sermon_recommended`(첫 번째가 `📩 203 대예배 설교`),
조각용은 `axes.world.fragment_recommended` 를 권한다.

### 3번 — 분류를 쓰지 않는다

`use_word: false`. 조각 분해와 성경구절 링크는 그대로 동작한다.

### 1번·2번 공통 — 구분과 분류를 짝지어 둔다

질문 3에서 정한 구분마다 어떤 World 값을 붙일지 확인한다 → `sermon_kinds.world_by_kind`.
프리셋이면 `axes.world.kind_hint` 를 제안값으로 쓴다(예: `새벽기도회` → `📩 203 대예배 설교`).
목사님 분류표면 `sermon_subset.world.values` 중에서 고르게 한다.

아래는 **함께 켜고 따로 묻지 않는다**:

```json
"use_word": true,
"route_scalar": true,
"single_world": true,
"wrap_values_in_wikilink": true,
"fragment_world": "{조각용 World 값}"
```

`fragment_world` 는 프리셋의 `axes.world.fragment_recommended`, 또는 목사님 분류표의
`sermon_subset.world.fragment_candidate` 를 제안한다. 없으면 비워 둔다.

---

## 질문 7. 이렇게 설정할까요?

```text
이렇게 설정하겠습니다.

  볼트          {vault}
  설교 원고      {input}  ({형식별 개수})
  설교 구분      {sermon_kinds.values}  →  {속성 / 파일명 / 폴더 분리}
  설교 노트      {main_folder}
  설교 조각      {fragment_folder}
  분류          {목사님 분류표 / 강의 표준 / 사용 안 함}
  노트 이름      {main_note_pattern}  (예: 260208_주일대예배_은혜의 복음_엡2_8.md)
  성경구절 링크   [[요3_16]]
  같은 이름 노트  멈추고 물어봅니다

저장할까요? 저장하려면 "OK 저장"이라고 답해 주세요.
```

저장 후:

1. `python3 scripts/config_loader.py "{config}"` 로 유효성 확인
2. 설교 **한 편**으로 dry-run 미리보기까지 보여주고, 실제 쓰기는 목사님 승인 뒤에
