# Onboarding Prompt

목표: 목사님 컴퓨터와 Obsidian vault 구조에 맞는 `pastor-sermon-import` 설정을 만든다.

기본 골격은 `pastor-sermon-basic` 과 같다 — **어디서 가져와, 어떻게 나눠서, 어디에 넣을지**를
먼저 정하고, 세밀한 항목(파일명 형식·충돌 정책·검증 규칙)을 뒤에서 직접 지정한다.
질문은 14개다.

## 진행 원칙

- 한 번에 한 질문만 한다.
- 답을 받으면 임시 설정에 기록한다.
- 모르면 선택지를 제시한다. 기본값이 있으면 기본값을 먼저 권한다.
- 목사님 컴퓨터와 볼트를 먼저 훑어 후보를 제안한다. 빈칸을 타이핑하게 두지 않는다.
- 실제 파일 쓰기 전 설정 미리보기를 보여준다.
- 목사님이 승인하면 설정 파일을 생성한다.
- 저장 경로는 `python3 scripts/paths.py` 가 알려주는 값을 쓴다.
- 목사님의 원고·노트·템플릿은 읽기만 한다.

---

## 1. Obsidian vault 폴더 경로가 어디인가요?

볼트 구조와 분류 정본·설교 템플릿을 함께 파악한다.

```bash
python3 scripts/find_word_template.py "{볼트 경로}"
```

`sermon_templates` 가 잡히면 목사님이 이미 쓰는 frontmatter 필드 이름·순서를 그대로 따른다.

## 2. 설교 원고를 어디서 가져올까요?

**항상 여쭤본다.** 볼트 안에 있다고 가정하지 않는다 — 구글 드라이브·원드라이브·
드롭박스·iCloud·문서 폴더 어디든 된다. 묻기 전에 후보를 만든다.

```bash
python3 scripts/find_sources.py            # 원고 폴더 후보 (형식별 개수·최근 수정일)
python3 scripts/find_sources.py --vaults   # 1번 질문의 볼트 후보
python3 scripts/suggest_folders.py "{볼트}" # 7·8번 질문의 폴더 후보
```

여러 폴더면 모두 받아 `input.sermon_sources` 배열에 넣는다. 원본은 읽기만 한다.
클라우드 폴더는 컴퓨터에 동기화(내려받기)되어 있어야 읽을 수 있다.

## 3. 그 폴더에 어떤 형식이 있나요? (확인 후 도구 준비)

```bash
python3 scripts/scan_inputs.py "{설교 폴더}"
```

- `by_suffix` 로 "워드 n편 · 한글 n편 · PDF n편" 을 보여준다
- `skipped[].note` 의 이유를 그대로 전한다 (`.gdoc` 링크 파일, `~$` 잠금 파일, 0바이트 파일)
- `ask_install` 이 있으면 **그 문구로 한 번 여쭙고** 승인 뒤에만 설치한다

```bash
python3 scripts/ensure_tools.py --check
python3 scripts/ensure_tools.py --install pdf,hwp
```

설치는 `<설정 홈>/tools/pylibs` 에만 한다. 실패하면 수동 방법(한글에서 `.txt`·`.hwpx`
저장, PDF 본문 복사)을 안내하고 읽을 수 있는 파일부터 진행한다.
`input.file_types` 는 실제로 가져오기로 한 형식만 남긴다.

## 4~6. 설교 구분 (세 단계)

```bash
python3 scripts/guess_naming.py "{설교 폴더}"
```

**4. 어떤 설교를 정리하시나요?** — 찾아낸 구분(`sermon_kinds_detected`)을 먼저 보여주고
다중 선택으로 확인한다. 못 찾았으면 흔한 구분을 제시한다.

```text
주일 대예배 · 주일 오후(저녁)예배 · 수요기도회 · 새벽기도회 · 금요기도회(철야) ·
특별집회·부흥회 · 청년부 · 청소년부(중고등부) · 어린이부(유년·유치부) ·
심방·경조사 · 성경공부·강의 · 구분하지 않음
```

**5. 원본에서 이 구분이 어떻게 나뉘어 있나요?** — 폴더로 / 파일명 표시로 / 섞여 있음.
실제 파일 6개를 어떻게 읽었는지 표로 보여주고 확인만 받는다.
→ `naming.folder_to_target`(폴더 이름 → 정식 구분명) · `sermon_kinds.marker_to_kind`
(`새벽` → `새벽기도회`) · `naming.target_markers`

**6. 노트에서는 어떻게 나눌까요?**

| 선택 | 설정 |
|---|---|
| 노트 속성으로만 | `sermon_kinds.frontmatter_key: "설교구분"` |
| 파일명에 표시 | `naming.main_note_pattern` 에 `{kind}` (짧은 표시는 `{target}`) |
| 구분마다 폴더 | `sermon_kinds.folder_by_kind` — 구분별 폴더를 이어서 여쭤본다 |
| 속성 + 파일명 (권장) | 위 두 개를 함께 |
| 구분하지 않음 | `sermon_kinds.enabled: false` |

`sermon_kinds.values` 에 선언한 구분만 인정한다. 매핑에 선언되지 않은 구분이 들어가면
설정 로드가 거부된다 — 오타로 엉뚱한 폴더에 조용히 쌓이는 일을 막는다.

## 7. 메인 설교 노트는 vault 안 어느 폴더에 저장할까요?

구분마다 폴더를 나누기로 했으면 구분별로 확인한다. 나머지는 `output.main_sermon_folder`.

## 8. 설교 조각 노트는 vault 안 어느 폴더에 저장할까요?

## 9. 분류 체계(WORD)를 쓰시겠습니까?

세 가지 중 하나를 골라 주세요.

**(1) 목사님이 이미 쓰는 분류 목록이 있다** — 그 노트를 읽어 오겠습니다
1번 질문의 `find_word_template.py` 결과(`word_sources`)를 후보로 먼저 제시한다.
정본은 대개 옵시디언 템플릿 폴더나 900번대 세팅 폴더에 있다.

```bash
python3 scripts/parse_word_source.py "{노트 경로}" --sermon-only
```

`--sermon-only` 는 설교 임포트에 실제로 쓰이는 값만 골라 준다.

| 축 | 부분집합 |
|---|---|
| World | 설교·사역 성격의 값 (`sermon_subset.world.values`) |
| Outcome | 이름에 `설교` 가 든 값 하나 |
| Route | 전체를 허용 목록에 두고 **`완료` 성격 값을 기본 추천** |
| Doctrine | 목사님 목록 전체 — 신학 주제는 설교마다 달라 좁히지 않는다 |

`sermon_subset.ask` 의 질문을 순서대로 여쭤본다. Route 확인이 그중 핵심이다:

```text
설교는 이미 설교하신 완성 원고라, 진행 단계는 '📝완료' 로 넣겠습니다. 괜찮으신가요?
```

인식 결과도 함께 확인받는다 — `World 소분류 {N}개 · Outcome {O}개 · Route {R}개 ·
Doctrine {D}개`. 못 읽은 축이 있으면 그 축의 값이 노트에서 어떤 모양인지 여쭤본다.

| 축 | 모양 |
|---|---|
| World 소분류 | `[[📩 203 대예배 설교]]` |
| World 대분류 | `[[📖 200 설교 & 사역]]` |
| Outcome | `[[🏷️ 설교]]` |
| Route | `[[📝완료]]` |
| Doctrine | `[[🔖칭의]]` |

접두어가 다르면 `--prefix world=🌍` 처럼 알려 주시면 되고, 접두어를 아예 쓰지 않으시면
`--generic` 으로 읽는다. 자세한 계약은 `python3 scripts/parse_word_source.py --explain`.
**목사님 노트는 고치지 않는다.**

**(2) 강의 표준 프리셋을 쓴다** — 가장 빠릅니다 (`data/word_preset.a4p.json`)

- World(지식 영역) 대분류 9개 · 소분류 69개
- Outcome(활용 목적) 9개 · Route(진행 단계) 4개
- Doctrine(신학 주제) 179개 — 성경학·조직신학·실천신학·영성·삶·절기 6개 묶음

설교에 실제로 쓰이는 값은 `axes.world.sermon_recommended`(첫 번째가 `📩 203 대예배 설교`),
Outcome `🏷️ 설교`, Route `📝완료`, Doctrine 3~6개다. 나머지는 목록으로만 들고 있고,
목록에 없는 값은 스킬이 절대 새로 만들지 않는다.

**(3) 분류를 쓰지 않는다** — 이후 분류 질문을 모두 건너뜁니다
성경구절 링크와 조각 분해는 그대로 동작한다. 나중에 언제든 켤 수 있다.

## 10. (분류를 쓸 때) 구분과 분류를 짝지어 둘까요?

질문 4에서 정한 구분마다 어떤 World 값을 붙일지 확인한다 → `sermon_kinds.world_by_kind`.
프리셋이면 `axes.world.kind_hint` 가 제안값이다 (예: `새벽기도회` → `📩 203 대예배 설교`).
이어서 아래를 확인한다.

- 조각 노트에 공통으로 붙일 World 값 → `classification.fragment_world`
  (프리셋 기본값은 `📩 206 설교 조각 & 영감`. 조각에는 Outcome·Route를 붙이지 않는 것이 표준)
- Route를 값 하나만 쓰는 방식(`route: "[[📝완료]]"`) → `classification.route_scalar: true`
- 분류값을 `[[ ]]` 링크로 넣기 (권장) → `classification.wrap_values_in_wikilink: true`
- 설교 한 편에 World를 하나만 붙이도록 검사 (권장) → `classification.single_world: true`

## 11. 성경구절 노트가 이미 있나요?

있다면 어느 폴더인가요? 알려 주시면 링크가 빨간색으로 남는 구절이 몇 개인지 검증 단계에서
함께 보고한다.

## 12. 성경구절 wikilink 형식

기본값은 `[[요3_16]]` (강의 공통 표준)이다. 이대로 쓸지 여쭙고, 바꾸려면 `{normalized}` 가
들어간 형식으로 받는다.

## 13. 메인 노트와 조각 노트의 파일명 규칙

- 기본값: 메인 `{date}_{title}_{main_passage}.md`, 조각 `{sermon_id}_{title}.md`
- 쓸 수 있는 값: `{date}`(2026-02-08) `{yymmdd}`(260208) `{kind}`(주일대예배)
  `{target}`(짧은 표시) `{title}` `{main_passage}` `{sermon_id}` `{index}`
- 구분을 파일명에 넣는 형식: `{yymmdd}_{kind}_{title}_{main_passage}.md`
  (예: `260208_주일대예배_은혜의 복음_엡2_8.md`)
- **조각을 나중에 재사용·병합하시려면 조각은 `{title}.md` 로 두셔야 합니다.**
  파일명이 제목과 같아야 같은 조각을 다시 찾을 수 있다.

## 14. 이미 같은 이름의 노트가 있을 때 어떻게 할까요?

- 메인 설교 노트: 기본 `ask`(멈추고 물어보기), `skip`(건너뛰기)
- 설교 조각 노트: → `naming.fragment_collision_policy`
  - `skip` (기본) — 기존 조각은 손대지 않고, 메인 노트의 링크만 그 조각으로 연결합니다.
    새 글머리는 보고에만 남습니다. 가장 보수적입니다.
  - `merge` — 기존 조각 **끝에 새 글머리만 추가**합니다. frontmatter(분류·날짜)는
    그대로 두고, 중복 글머리는 넣지 않습니다. 설교를 임포트할수록 조각이 자랍니다.
  - `ask` — 병합 대상을 보여주고 그때 물어봅니다.

---

## 마지막 출력

설정 미리보기를 JSON 형태로 보여주고 다음 질문을 한다.

```text
이 설정으로 저장할까요? 저장하려면 "OK 저장"이라고 답해 주세요.
```

저장 후 `python3 scripts/config_loader.py "{config}"`로 유효성을 확인하고,
설교 샘플 1개로 dry-run 미리보기까지 보여준다.
