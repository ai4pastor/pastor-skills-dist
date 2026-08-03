---
name: pastor-sermon-basic
description: 설교 파일(.docx/.hwp/.hwpx/.pdf/.md/.txt)을 Obsidian에 정리하는 가장 간단한 방법. 원고가 구글 드라이브·원드라이브에 있어도 찾아서 가져오고, 설교 구분(대예배·수요·새벽)을 물어 나눠 준다. 트리거 — "/pastor-sermon-basic", "설교 정리해줘", "설교 옵시디언에 넣어줘", "설교 임포트 쉽게".
---

# pastor-sermon-basic

설교를 Obsidian에 정리하는 **가장 간단한 경로**다.

목사님이 답할 것은 **어디서 가져와, 어떻게 나눠서, 어디에 넣을지**뿐이다.
파일명 규칙·분류 방식·저장 형식은 스킬이 컴퓨터와 볼트를 읽어 추론하고 **확인만 받는다**.

만들어지는 것은 세밀한 설정 버전(`pastor-sermon-import`)과 같다:

- 메인 설교 노트 1개 — 원본 설교문 전체 보존 + 조각별 요약 링크
- 설교 조각 노트 N개 — 논지·해석·예화·적용 단위로 분해, 예화는 `💡` 표시
- 성경구절 전부 `[[요3_16]]` 형태로 링크
- (분류를 쓰시면) WORD frontmatter

## 핵심 원칙 (절대 위반 금지)

1. 원본 설교 파일은 절대 수정·이동·삭제하지 않는다.
2. 기존 Obsidian 노트는 절대 덮어쓰지 않는다.
3. 실제 쓰기 전 항상 dry-run 미리보기를 먼저 보여준다.
4. 목사님이 명시적으로 승인하기 전에는 vault에 파일을 생성하지 않는다.
5. 분류값은 config 허용 목록 안에서만 고른다. 목록에 없는 값은 비슷해 보여도 만들지 않는다.
6. tags는 한 단어 한국어, 띄어쓰기 금지.
7. frontmatter는 YAML 표준 파서로 다루지 않는다 — `"[[...]]"` 값이 파괴된다.
8. 저장 경로는 산문에서 추측하지 말고 `scripts/paths.py` 출력을 쓴다.

## 명령: `/pastor-sermon-basic [설교 파일 또는 폴더]`

명령은 하나다. 설정이 없으면 먼저 설정하고, 있으면 바로 정리한다.

```bash
python3 scripts/paths.py --ensure
```

출력의 `config`·`fragments`·`word`를 이후 `{config}`·`{fragments}`·`{word}`로 쓴다.
`config_exists`가 `false`면 **A. 첫 설정**부터, `true`면 **B. 정리**부터 진행한다.

---

## A. 첫 설정 (한 번만)

`prompts/onboarding.md`를 따라 **한 번에 한 질문씩** 진행한다.
질문은 7개이고, 나머지는 아래 스크립트들이 대신 답한다.

### A-1. 볼트와 원고 위치를 찾는다

```bash
python3 scripts/find_sources.py --vaults     # 옵시디언 볼트 후보
python3 scripts/find_sources.py             # 설교 원고 폴더 후보
```

`find_sources.py`는 구글 드라이브·원드라이브·드롭박스·iCloud·문서·다운로드까지 훑어
폴더별 **형식별 개수·최근 수정일·예시 파일명**을 돌려준다.
**설교 원고가 어디 있는지는 항상 여쭤본다** — 볼트 안에 있다고 가정하지 않는다.

볼트 경로를 받으면 곧바로:

```bash
python3 scripts/suggest_folders.py "{볼트 경로}"
```

- `sermon_folders` / `fragment_folders` / `bible_folders` — 폴더 후보 (점수·노트 수 포함)
- `word_notes` — 분류 정본 후보 (템플릿 폴더·900번대 세팅 폴더를 먼저 본다)
- `sermon_templates` — 설교 템플릿과 그 frontmatter 키 순서

**후보를 그대로 선택지로 제시한다.** 빈칸을 타이핑하게 두지 않는다.

### A-2. 형식을 확인하고 필요한 도구를 준비한다

```bash
python3 scripts/scan_inputs.py "{설교 폴더}"
```

- `by_suffix` — 워드·한글·PDF가 각각 몇 편인지
- `skipped[].note` — 건너뛴 이유 (구글 드라이브 링크 파일 `.gdoc`, 워드 잠금 파일 `~$`,
  아직 안 내려온 0바이트 파일, 미지원 형식)
- `ask_install` — 이 문구로 **한 번** 여쭙고, 승인 뒤에만 설치한다
- `ask_undeclared` — 설정에 없는 형식이 있을 때 함께 가져올지 여쭤본다

```bash
python3 scripts/ensure_tools.py --check
python3 scripts/ensure_tools.py --install pdf,hwp     # 승인 뒤에만
```

설치는 **스킬 전용 폴더**(`<설정 홈>/tools/pylibs`)에만 한다. 실패하면 수동 방법
(한글에서 `.txt`·`.hwpx` 로 저장 등)을 안내하고, 읽을 수 있는 파일부터 진행한다.

### A-3. 설교 구분을 정한다

```bash
python3 scripts/guess_naming.py "{설교 폴더}"
```

- `sermon_kinds_detected` — 폴더·파일명에서 찾은 구분 (주일대예배·수요기도회·새벽기도회 …)
- `sermon_kind_hits` — 어디서 찾았는지 (폴더 / 파일명 표시 / 파일명 어디든)
- `date_kind`·`date_ratio` — 날짜 표기와 그 비율
- `target_markers` — 위치 기반 표시만 인정 (한 번만 나온 두 글자 이상 토큰은 제목
  첫 단어일 수 있어 제외)
- `pattern_options` — 구분을 파일명에 넣는 형식 / 짧은 표시 / 구분 없음
- `suggested` — config에 그대로 넣을 값 (`naming.*` + `sermon_kinds.*`)
- `samples` — 실제 파일 6개를 어떻게 읽었는지

**`explain`과 `samples`를 보여주고 "이렇게 읽었습니다, 맞습니까?"로 확인만 받는다.**
그다음 노트에서 어떻게 나눌지 여쭤본다 — 속성 / 파일명 / 구분별 폴더 (권장: 속성+파일명).

### A-4. 분류(WORD)

`suggest_folders.py`의 `word_notes`에 후보가 있으면:

```bash
python3 scripts/parse_word_source.py "{볼트}/{후보 경로}" --sermon-only
```

`--sermon-only`는 **설교에 쓰이는 값만** 골라 준다 — 설교 성격의 World 값,
Outcome `설교`, Route는 `완료` 추천, Doctrine은 목사님 목록 전체(신학 주제는
설교마다 다르다). `sermon_subset.ask` 의 질문을 순서대로 여쭤본다.

후보가 없으면 `python3 scripts/find_word_template.py "{볼트}"` 로 한 번 더 찾고,
그래도 없으면 두 가지를 제시한다 — 강의 표준 프리셋(`data/word_preset.a4p.json`)을
쓸지, 분류 없이 쓸지.

분류를 쓰기로 하면 아래를 **함께 켠다** (따로 묻지 않는다):

```json
"route_scalar": true,
"single_world": true,
"wrap_values_in_wikilink": true,
"fragment_world": "{조각용 World 값}"
```

구분마다 붙일 World 값도 확인해 `sermon_kinds.world_by_kind`에 넣는다.
프리셋이면 `axes.world.kind_hint`가 제안값이다.
조각용 World 값은 프리셋의 `axes.world.fragment_recommended`, 또는 목사님 분류표의
`sermon_subset.world.fragment_candidate`를 제안한다.

### A-5. 나머지는 고정값

묻지 않고 아래로 정한다.

| 항목 | 값 | 이유 |
|---|---|---|
| 조각 파일명 | `{title}.md` | 파일명이 제목과 같아야 나중에 같은 조각을 다시 찾을 수 있다 |
| 성경구절 링크 | `[[요3_16]]` | 강의 공통 표준 |
| 같은 이름 메인 노트 | `ask` (멈추고 물어봄) | 덮어쓰기 사고를 막는다 |
| 같은 이름 조각 | `skip` (기존 조각 유지, 링크만 연결) | 기존 노트를 건드리지 않는 가장 보수적인 선택 |
| 로그 | `.vault-sermon-import/logs` | 볼트 안, 눈에 띄지 않는 위치 |

### A-6. 저장

완성된 config 미리보기를 보여주고 `"OK 저장"` 승인을 받은 뒤 `{config}`에 저장한다.
그다음 `python3 scripts/config_loader.py "{config}"`로 유효성을 확인하고,
설교 한 편으로 아래 dry-run까지 시연한다.

---

## B. 설교 정리

### B-1. 준비 확인

```bash
python3 scripts/config_loader.py "{config}"
python3 scripts/scan_inputs.py "{입력 경로}" --config "{config}"
```

지원 형식은 `.docx` / `.hwp` / `.hwpx` / `.pdf` / `.md` / `.txt`.
`ask_install` 이 있으면 승인받아 `ensure_tools.py --install` 을 먼저 돌린다.
건너뛴 파일은 이유와 함께 보고에 남긴다.

### B-2. 텍스트 추출 (파일별)

```bash
python3 scripts/extract_text.py "{파일 경로}"
```

JSON의 `text`가 분석 대상 본문이다. 원본 파일은 읽기 전용이다.
`warnings` 가 있으면 목사님께 그대로 전한다 — `scanned_pdf`(글자 없는 스캔 이미지)와
`short_text`(본문이 200자 미만)는 그 설교를 그냥 넘기면 빈 노트가 된다는 신호다.

### B-3. 조각 분해

먼저 이미 있는 조각 제목을 확인한다:

```bash
python3 scripts/list_fragments.py --config "{config}"
```

목록에 **의미가 같은 제목이 있으면 그 제목을 글자 그대로 쓴다.** 한 글자만 달라도
다른 파일이 되어 같은 생각이 두 벌로 갈라진다.

그다음 `prompts/split_fragments.md`의 규칙을 그대로 따라 분해하고 `{fragments}`에 저장한다:

```json
{
  "{입력 파일명}": [
    {
      "title": "명제형 조각 제목",
      "kind": "argument|exposition|illustration|application|doctrine",
      "bullets": ["본문 근거가 있는 요약 글머리"],
      "doctrine": ["허용 목록 안의 값"],
      "tags": ["한단어태그"]
    }
  ]
}
```

- 예화는 `kind: illustration` + 제목을 `💡 {비유명} - {핵심 메시지}` 형식으로.
- `doctrine`은 허용 목록 안에서 그 조각 내용 기준 1~3개. 분류를 안 쓰면 생략.

### B-4. 분류 제안 (분류를 쓸 때만)

`prompts/word_classify.md`를 따라 설교 전체 분류를 제안하고 `{word}`에 저장한다.

```json
{
  "{입력 파일명}": {
    "world": ["허용 목록 값 1개"],
    "outcome": ["허용 목록 값 1개"],
    "route": ["허용 목록 값 1개"],
    "doctrine": ["허용 목록 값 3~6개"],
    "tags": ["한단어태그 3~8개"]
  }
}
```

### B-5. 미리보기 (dry-run)

```bash
python3 scripts/build_notes.py "{입력 경로}" \
  --config "{config}" --fragments "{fragments}" --word "{word}"
```

목사님께 보여줄 것: 만들어질 파일 목록, 조각 제목들, 구분별 편수(`by_sermon_kind`),
충돌(`conflicts`), 건너뜀(`skips`), 경고(`warnings`), 분류 제안값.

경고에 "허용 목록 밖 값 제외"가 있으면 B-3~B-4의 JSON을 고쳐 다시 미리보기한다.

### B-6. 승인 후 쓰기

목사님이 명시적으로 승인한 경우에만:

```bash
python3 scripts/build_notes.py "{입력 경로}" \
  --config "{config}" --fragments "{fragments}" --word "{word}" \
  --write --approve WRITE
```

출력의 `manifest` 경로를 기억한다.

### B-7. 검증 (필수)

```bash
python3 scripts/verify_output.py "{manifest 경로}" --config "{config}"
```

`status`가 `blocked`면 **보고 전에 반드시 고친다** — 깨진 링크는 메인 노트의 링크를
실제 조각 파일명으로, 허용 목록 밖 값은 허용 값으로 Edit한 뒤 재실행해 `ok`를 확인한다.

### B-8. 보고

```text
정리 완료: {N}편  ({구분별 편수})
메인 노트: {경로}
설교 조각: 신규 {A}개 · 건너뜀 {B}개
성경구절: {M}개 링크 · 확인 필요 {K}개
분류: {요약, 분류를 쓸 때}
읽지 못한 파일: {있으면 이유와 함께}
경고: {있으면}
로그: {manifest 경로}
```

빨간 링크(아직 노트가 없는 성경구절)가 있으면 그것이 정상이라는 사실을 함께 알린다.

---

## 세밀한 설정이 필요해지면

아래를 원하시면 `pastor-sermon-import`를 안내한다. 설정 파일은 호환되므로
그대로 이어서 쓸 수 있다.

- 같은 제목 조각에 새 글머리를 **병합**해 조각을 키우기
- 파일명 형식을 직접 지정하기
- 분류 허용 목록을 축별로 골라 쓰기
- 분류값 접두어 검사 등 검증 규칙을 켜고 끄기

## 제공 스크립트

- `scripts/paths.py` — 설정·작업파일 경로 (모든 단계의 경로 출처)
- `scripts/find_sources.py` — 컴퓨터에서 볼트·설교 원고 폴더 찾기 (클라우드 포함)
- `scripts/suggest_folders.py` — 볼트를 읽어 폴더·분류 정본·설교 템플릿 후보 제시
- `scripts/find_word_template.py` — 옵시디언 템플릿 폴더 설정·900번대 세팅 폴더에서 분류 정본 찾기
- `scripts/guess_naming.py` — 설교 구분과 파일명 규칙 추론
- `scripts/parse_word_source.py` — 분류 노트에서 허용 목록 추출 (`--sermon-only`: 설교용 부분집합)
- `scripts/ensure_tools.py` — 형식별 변환 도구 점검·격리 설치
- `scripts/list_fragments.py` — 기존 조각 제목 목록
- `scripts/config_loader.py` — 설정 로드·검증
- `scripts/scan_inputs.py` · `extract_text.py` · `extract_meta.py` · `extract_bible_refs.py`
- `scripts/build_notes.py` — 미리보기 / `--write --approve WRITE`일 때만 실제 생성
- `scripts/verify_output.py` — 결과 검증
