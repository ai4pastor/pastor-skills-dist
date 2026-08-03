---
name: pastor-sermon-basic
description: 설교 파일(.docx/.md/.txt)을 Obsidian에 정리하는 가장 간단한 방법. 폴더 위치 몇 개만 답하면 메인 설교 노트 + 설교 조각 노트 + 성경구절 링크가 자동으로 만들어진다. 트리거 — "/pastor-sermon-basic", "설교 정리해줘", "설교 옵시디언에 넣어줘", "설교 임포트 쉽게".
---

# pastor-sermon-basic

설교를 Obsidian에 정리하는 **가장 간단한 경로**다.

목사님이 답할 것은 폴더 위치뿐이다. 파일명 규칙·분류 방식·저장 형식은
스킬이 볼트를 읽어 추론하고 **확인만 받는다**.

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

## A. 첫 설정 (한 번만, 5분)

`prompts/onboarding.md`를 따라 **한 번에 한 질문씩** 진행한다.
질문은 5개이고, 나머지는 아래 두 스크립트가 대신 답한다.

### A-1. 볼트를 읽어 후보를 만든다

목사님이 볼트 경로를 알려주면 곧바로:

```bash
python3 scripts/suggest_folders.py "{볼트 경로}"
```

- `sermon_folders` / `fragment_folders` / `bible_folders` — 폴더 후보 (점수·노트 수 포함)
- `word_notes` — 분류 정리 노트 후보 (어느 축이 몇 개 발견됐는지)

**후보를 그대로 선택지로 제시한다.** 빈칸을 타이핑하게 두지 않는다.
후보가 없으면 새로 만들 폴더 이름을 여쭤본다.

### A-2. 파일명 규칙을 추론한다

설교 원본 폴더를 알려주면:

```bash
python3 scripts/guess_naming.py "{설교 폴더}"
```

- `date_kind`·`date_ratio` — 날짜 표기와 그 비율
- `target_markers` — 2회 이상 반복된 대상 표시만 인정 (한 번만 나온 토큰은 제목 첫 단어일 가능성이 높아 제외)
- `folder_to_target` — 폴더명에서 추론한 대상 대응
- `suggested` — config에 그대로 넣을 값
- `samples` — 실제 파일 6개를 어떻게 읽었는지

**`explain`과 `samples`를 목사님께 보여주고 "이렇게 읽었습니다, 맞습니까?"로 확인만 받는다.**
틀리면 고치고, 맞으면 `suggested`를 그대로 config에 넣는다.

### A-3. 분류(WORD)

`suggest_folders.py`의 `word_notes`에 후보가 있으면:

```bash
python3 scripts/parse_word_source.py "{볼트}/{후보 경로}"
```

인식한 개수(World·Outcome·Route·Doctrine)를 보여주고 확인받는다.
후보가 없으면 두 가지를 제시한다 — 강의 표준 프리셋(`data/word_preset.a4p.json`)을
쓸지, 분류 없이 쓸지.

분류를 쓰기로 하면 아래를 **함께 켠다** (따로 묻지 않는다):

```json
"route_scalar": true,
"single_world": true,
"wrap_values_in_wikilink": true,
"fragment_world": "{조각용 World 값}"
```

조각용 World 값은 프리셋의 `axes.world.fragment_recommended`, 또는 목사님 분류 노트에서
조각·영감 성격의 값을 찾아 제안한다.

### A-4. 나머지는 고정값

묻지 않고 아래로 정한다.

| 항목 | 값 | 이유 |
|---|---|---|
| 조각 파일명 | `{title}.md` | 파일명이 제목과 같아야 나중에 같은 조각을 다시 찾을 수 있다 |
| 성경구절 링크 | `[[요3_16]]` | 강의 공통 표준 |
| 같은 이름 메인 노트 | `ask` (멈추고 물어봄) | 덮어쓰기 사고를 막는다 |
| 같은 이름 조각 | `skip` (기존 조각 유지, 링크만 연결) | 기존 노트를 건드리지 않는 가장 보수적인 선택 |
| 로그 | `.vault-sermon-import/logs` | 볼트 안, 눈에 띄지 않는 위치 |

### A-5. 저장

완성된 config 미리보기를 보여주고 `"OK 저장"` 승인을 받은 뒤 `{config}`에 저장한다.
그다음 `python3 scripts/config_loader.py "{config}"`로 유효성을 확인하고,
설교 한 편으로 아래 dry-run까지 시연한다.

---

## B. 설교 정리

### B-1. 준비 확인

```bash
python3 scripts/config_loader.py "{config}"
python3 scripts/scan_inputs.py "{입력 경로}"
```

지원 형식은 `.docx`(pandoc 또는 python-docx 필요) / `.md` / `.txt`.
미지원 파일은 건너뛰고 보고에 남긴다.

### B-2. 텍스트 추출 (파일별)

```bash
python3 scripts/extract_text.py "{파일 경로}"
```

JSON의 `text`가 분석 대상 본문이다. 원본 파일은 읽기 전용이다.

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

목사님께 보여줄 것: 만들어질 파일 목록, 조각 제목들, 충돌(`conflicts`),
건너뜀(`skips`), 경고(`warnings`), 분류 제안값.

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
정리 완료: {N}편
메인 노트: {경로}
설교 조각: 신규 {A}개 · 건너뜀 {B}개
성경구절: {M}개 링크 · 확인 필요 {K}개
분류: {요약, 분류를 쓸 때}
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
- `scripts/suggest_folders.py` — 볼트를 읽어 폴더·분류 노트 후보 제시
- `scripts/guess_naming.py` — 설교 파일명 규칙 추론
- `scripts/parse_word_source.py` — 분류 노트에서 허용 목록 추출
- `scripts/list_fragments.py` — 기존 조각 제목 목록
- `scripts/config_loader.py` — 설정 로드·검증
- `scripts/scan_inputs.py` · `extract_text.py` · `extract_meta.py` · `extract_bible_refs.py`
- `scripts/build_notes.py` — 미리보기 / `--write --approve WRITE`일 때만 실제 생성
- `scripts/verify_output.py` — 결과 검증
