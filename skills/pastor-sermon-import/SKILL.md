---
name: pastor-sermon-import
description: 목회자의 기존 설교 파일(.docx/.hwp/.hwpx/.pdf/.md/.txt)을 개인 Obsidian vault 구조에 맞게 메인 설교 노트 + 설교 조각 노트 + 성경구절 wikilink + WORD/분류 frontmatter로 자동 import하는 스킬. 원고가 구글 드라이브·원드라이브에 있어도 찾아서 가져오고, 설교 구분(대예배·수요·새벽)별로 나눠 준다. 트리거 — "/pastor-sermon-setup", "/pastor-sermon-import [경로]", "설교 옵시디언으로 정리해줘", "설교 import".
---

# pastor-sermon-import

목사님이 가진 설교 자료를 자기 Obsidian vault에 맞게 자동 정리하는 스킬이다.
한 번 실행하면 메인 설교 노트 1개 + 의미 단위로 분해된 설교 조각 노트 N개가
분류·연결된 상태로 생성된다.

## 핵심 원칙 (절대 위반 금지)

1. 원본 설교 파일은 절대 수정·이동·삭제하지 않는다.
2. 기존 Obsidian 노트는 절대 덮어쓰지 않는다.
3. 실제 쓰기 전 항상 dry-run 미리보기를 먼저 보여준다.
4. 목사님이 명시적으로 승인하기 전에는 vault에 파일을 생성하지 않는다.
5. WORD/doctrine 값은 **config 허용 목록 안에서만** 고른다. 목록에 없는 값은 비슷해 보여도 절대 새로 만들지 않는다.
6. tags는 한 단어 한국어, **띄어쓰기 금지**.
7. frontmatter는 YAML 표준 파서로 다루지 않는다 — `"[[...]]"` 값이 파괴된다. 스크립트가 생성하는 형식을 그대로 쓴다.
8. 설정은 JSON 단일 계약이다. **저장 경로를 문장에서 추측하지 말고 `scripts/paths.py`가 알려주는 값을 쓴다** (Step 0). 목사님이 vault 안에 두기를 원하면 `<vault>/.vault-sermon-import/config.json`도 자동 인식된다.

## 명령 1: `/pastor-sermon-setup` — 최초 설정

목사님 환경을 인터뷰하고 설정 파일을 만든다. `prompts/onboarding.md`를 따라
**한 번에 한 질문씩** 진행한다.

절차:

0. `python3 scripts/paths.py --ensure`를 실행한다. 출력의 `config` 값이 아래에서 쓸 `{config}`다.
1. `prompts/onboarding.md`의 질문 순서대로 인터뷰한다. 묻기 전에 후보를 만든다:
   - `python3 scripts/find_sources.py --vaults` / `python3 scripts/find_sources.py` —
     볼트와 **설교 원고 폴더**(구글 드라이브·원드라이브·iCloud 포함) 후보
   - `python3 scripts/suggest_folders.py "{볼트}"` — 저장 폴더·분류 정본·설교 템플릿 후보
   - `python3 scripts/find_word_template.py "{볼트}"` — 옵시디언 템플릿 폴더 설정과
     900번대 세팅 폴더에서 분류 정본 찾기
   - `python3 scripts/guess_naming.py "{설교 폴더}"` — 설교 구분·날짜·파일명 규칙 추론
   - `python3 scripts/scan_inputs.py "{설교 폴더}"` → `ask_install` 이 있으면 그 문구로
     한 번 여쭙고 승인 뒤 `python3 scripts/ensure_tools.py --install {형식}`
   - 9번(분류 체계)에서 **강의 표준 프리셋**을 고르면 `data/word_preset.a4p.json`을 읽어 허용 목록을 채운다. 프리셋은 목사님이 고른 뒤에만 config로 들어간다 — 기본값으로 심지 않는다.
   - **목사님이 이미 쓰는 분류 노트**가 있으면 `python3 scripts/parse_word_source.py "{노트 경로}" --sermon-only`로 읽는다. 설교에 쓰이는 값만 확인하면 된다. 그 노트는 수정하지 않는다.
2. 답변으로 config JSON을 구성한다. 형식은 `examples/config.example.json`과 동일해야 한다.
3. 완성된 config 미리보기를 보여주고 "OK 저장" 승인을 받는다.
4. `{config}`에 저장한다.
5. `python3 scripts/config_loader.py "{config}"`로 유효성을 확인한다.
6. 설교 샘플 1개로 아래 import 절차의 dry-run까지만 실행해 결과를 보여준다.

터미널에 익숙한 목사님이라면 `python3 scripts/setup_profile.py` 대화형 위저드를 대신 안내해도 된다.

## 명령 2: `/pastor-sermon-import [파일 또는 폴더]` — 실제 import

### Step 0. 경로 확인 (항상 먼저)

```bash
python3 scripts/paths.py --ensure
```

출력의 `config`·`fragments_dir`·`word_dir`를 이후 단계에서 각각 `{config}`·`{fragments_dir}`·`{word_dir}`로 쓴다.
**경로를 직접 타이핑하지 않는다** — 목사님 환경에 따라 저장 위치가 달라진다.
`{fragments_dir}`·`{word_dir}`에 이전 실행의 청크 파일이 남아 있으면 새 import 를 시작하기 전에 비운다
(이어서 하는 재실행이면 그대로 둔다 — 이미 분석한 묶음을 다시 분석하지 않아도 된다).

### Step 1. 준비 확인

```bash
python3 scripts/config_loader.py "{config}"                    # 설정 유효성
python3 scripts/scan_inputs.py "{입력 경로}" --config "{config}"  # 입력 파일 스캔
```

- config가 없으면 import를 진행하지 말고 `/pastor-sermon-setup`을 먼저 안내한다.
- 지원 형식: `.docx` / `.hwp` / `.hwpx` / `.pdf` / `.md` / `.txt`.
  `ask_install`이 있으면 승인받아 `python3 scripts/ensure_tools.py --install {형식}`을 먼저 돌린다.
- `skipped`의 이유(`.gdoc` 링크 파일, `~$` 잠금 파일, 0바이트 파일, 미지원 형식)를 그대로 보고한다.
- `ask_undeclared`가 있으면 그 형식도 함께 가져올지 여쭙고 `input.file_types`를 늘린다.

### Step 2. 추출 + 분석 (5편씩 묶어서)

입력 파일을 **5편 안팎의 묶음(청크)으로 나눠** 묶음마다 아래 ①~④를 처리한다.
한 묶음이 끝나면 결과가 파일로 저장돼 있으므로 그 원고들은 잊고 다음 묶음으로
넘어간다 — 원고 수십 편을 동시에 기억하려 하면 대량 import 가 느려진다.
이 단계에서 목사님께 질문할 일은 없다. 묶음이 끝날 때마다 진행 상황만 한 줄로
알린다: `10/50편 정리 중…`

**① 추출** — 묶음의 파일별로:

```bash
python3 scripts/extract_text.py "{파일 경로}"
```

JSON의 `text`가 분석 대상 본문이다. 원본 파일은 읽기 전용이다. 추출 결과는
캐시되므로 이후 dry-run·실제 쓰기가 같은 변환을 반복하지 않는다.
`warnings`가 있으면 그대로 전한다 — `scanned_pdf`(글자 없는 스캔 이미지)와
`short_text`(본문 200자 미만)는 그냥 넘기면 빈 설교 노트가 된다는 신호다.

**② 분석 (설교마다 한 번에)** — 본문을 **한 번만** 읽고 두 가지를 함께 만든다:

- `prompts/split_fragments.md` 규칙 그대로 의미 단위 조각 분해
- `use_word: true`면 `prompts/word_classify.md` 규칙 그대로 설교 전체 WORD/분류 제안
  (조각을 다 나눈 직후가 설교 전체 주제를 가장 정확히 아는 순간이다)
- Step 0 출력에 `custom_rules_exists: true`가 있으면 그 파일(**나만의 규칙**)을 먼저 읽고
  문체·구성 규칙 위에 덧입힌다. 목사님이 "조각 문체를 바꾸고 싶다"고 하시면 스킬 파일을
  고치지 말고 이 파일을 만들어 드린다 — 업데이트해도 유지된다.

**③ 제목 대조** — 묶음의 조각 제목 초안들을 `{"titles": [...]}` JSON으로 모아
근접 후보만 받는다:

```bash
python3 scripts/list_fragments.py --config "{config}" --match-file "{초안 JSON}" --extra "{fragments_dir}"
```

초안마다 돌아온 후보 중 **의미가 같은 제목이 있으면 새로 짓지 말고 그 제목을
글자 그대로 쓴다.** 가운뎃점·공백·어순이 한 글자만 달라도 다른 파일이 되어 같은
생각이 두 벌로 갈라진다. `--extra` 덕분에 앞 묶음이 지은 제목과도 대조된다.
기존 조각이 수십 개 이하로 적으면 `--match-file` 없이 전체 목록을 받아 직접
대조한다 — 근접 매치는 초안과 어휘가 겹칠 때만 후보를 내므로, 어휘가 다른
같은 생각을 놓칠 수 있다.

**④ 저장** — 묶음 결과를 청크 파일 두 개로 저장한다 (묶음 번호대로 01, 02, …):

`{fragments_dir}/chunk-01.json`:

```json
{
  "{입력 파일명 또는 절대경로}": [
    {
      "title": "명제형 조각 제목",
      "kind": "argument|exposition|illustration|application|doctrine",
      "bullets": ["본문 근거가 있는 요약 글머리"],
      "doctrine": ["config 허용 목록 안의 값"],
      "tags": ["한단어태그"]
    }
  ]
}
```

- `doctrine`은 config의 `classification.doctrine_values` **안에서만**, 그 조각 내용 기준으로 1~3개.
- `use_word: false`면 `doctrine`을 생략한다. `tags`는 항상 넣는다.

`{word_dir}/chunk-01.json` (`use_word: false`면 만들지 않는다):

```json
{
  "{입력 파일명 또는 절대경로}": {
    "world": ["허용 목록 값 1~2개"],
    "outcome": ["허용 목록 값 1개"],
    "route": ["허용 목록 값 1개"],
    "doctrine": ["허용 목록 값 3~6개"],
    "tags": ["한단어태그 3~8개"]
  }
}
```

### Step 3. dry-run 미리보기

```bash
python3 scripts/build_notes.py "{입력 경로}" \
  --config "{config}" \
  --fragments "{fragments_dir}" \
  --word "{word_dir}" \
  --resume
```

추출은 Step 2의 캐시를 재사용하므로 여기서 파일을 다시 변환하지 않는다.
`--resume`은 이전 실행의 manifest에 기록된 원고를 자동으로 건너뛴다 — 대량
import 가 중간에 끊겨도 처음부터 다시 하지 않는다.

- 스크립트가 허용 목록 밖 doctrine/WORD 값을 자동으로 걸러내고 경고에 남긴다.
- 목사님께 보여줄 것: 생성될 파일 목록(경로), 구분별 편수(`by_sermon_kind`), 충돌(`conflicts`), **병합 대상(`merges`)**, 건너뜀(`skips`), 재개로 건너뜀(`resumed`), 경고(warnings), 조각 제목들, WORD 제안값.
- 구분을 알 수 없는 설교가 있으면 경고에 남는다. 기본 폴더로 들어간다는 사실을 알리고 진행 여부를 묻는다.
- "허용 목록 밖 값 제외" 경고는 **재실행이 필요 없다** — 스크립트가 이미 안전하게
  걸러냈다. 다만 그 때문에 world/outcome/route가 통째로 빈 파일이 있으면, 그 파일이
  든 청크 JSON만 허용 목록 안의 값으로 고쳐 dry-run을 다시 돌린다 (캐시 덕에 몇 초면 끝난다).
- 충돌이 있으면 해당 설교는 만들지 않는다는 사실을 알리고, **충돌만 건너뛰고
  나머지를 진행할지** 여쭙는다. 승인하시면 Step 4에서 `--skip-conflicts`를 붙인다.
- `merges`가 있으면 **파일 목록과 추가될 글머리 수를 보여주고 따로 승인받는다.** 병합은 기존 노트를 바꾸는 유일한 동작이다. 다만 frontmatter(분류·날짜)는 건드리지 않고 새 글머리만 끝에 붙으며, 중복 글머리는 추가되지 않는다.

### Step 4. 승인 후 실제 쓰기

목사님이 명시적으로 승인한 경우에만:

```bash
python3 scripts/build_notes.py "{입력 경로}" \
  --config "{config}" \
  --fragments "{fragments_dir}" \
  --word "{word_dir}" \
  --resume \
  --write --approve WRITE
```

충돌 건너뛰기를 승인받았다면 `--skip-conflicts`를 붙인다 — 충돌 설교만 manifest에
`skip_conflict`로 남고 나머지가 정상 생성된다. 승인 없이는 붙이지 않는다.

출력의 `manifest` 경로를 기억한다.

### Step 5. 검증 (필수)

```bash
python3 scripts/verify_output.py "{manifest 경로}" --config "{config}"
```

검증 항목: 파일 존재, vault 경계(구분별 폴더 라우팅 포함), 금지 문자, 조각 wikilink 해결,
WORD/doctrine 허용 목록, 설교 구분 속성이 선언된 값인지, tags 띄어쓰기.

`status`가 `blocked`면 **보고 전에 반드시 수정**한다:
- 깨진 wikilink → 메인 노트의 링크를 실제 조각 파일명으로 Edit
- 허용 목록 밖 값 → frontmatter를 허용 값으로 Edit
- 수정 후 verify 재실행 → `ok` 확인

### Step 6. 보고

```text
처리 완료: {N}개  ({구분별 편수})
메인 노트: {경로}
설교 조각: 신규 {A}개 · 병합 {C}개(글머리 +{D}개) · 건너뜀 {B}개
충돌로 건너뜀: {있으면 편수와 노트 이름}
이미 정리돼 건너뜀(재개): {resumed 있으면 편수}
성경구절: {M}개 추출 · 확인 필요 {K}개
분류: {WORD 요약, use_word일 때}
읽지 못한 파일: {있으면 이유와 함께}
경고: {있으면}
로그: {manifest 경로}
```

## 설교 조각 원칙

- 조각은 설교의 논증·해석·예화·적용 단위로 나눈다. 억지로 개수를 늘리지 않는다.
- 조각 제목은 명제형(내용이 드러나는 문장형)으로 짓고, Obsidian 금지 문자(`: ? / \ * < > | " # ^ [ ]`)를 쓰지 않는다.
- 메인 설교 노트에는 `## [[조각 파일명]]` + 글머리로 연결된다 (스크립트가 생성하므로 링크와 파일명이 어긋날 수 없다).
- 조각 노트의 doctrine/tags는 전체 설교가 아니라 **그 조각 내용 기준**으로 분류한다.
- 조각 노트에는 `## [[제목]]` 헤딩을 넣지 않는다. 옵시디언이 파일명을 제목으로 보여준다.
- `use_word`일 때 조각은 `classification.fragment_world` 값을 world로 갖고, **outcome·route는 갖지 않는다** — 그 둘은 완성된 설교를 설명하는 값이다.
- 같은 제목의 조각이 이미 있으면 `fragment_collision_policy`에 따른다. `merge`는 새 글머리만 끝에 붙이고 기존 frontmatter를 그대로 둔다 — 기존 값을 고치는 경로는 없다.

## 성경구절 원칙

- 본문의 모든 성경구절을 추출한다. 약어(`요 3:16`)와 풀어쓴 이름(`요한복음 3장 16절`) 모두 인식된다.
- 링크 형식 기본값은 `[[요3_16]]` (수강생 공통 표준). config `bible.link_style`로 변경 가능.
- 범위 구절은 `bible.range_policy`에 따라 개별 절 확장(기본) 또는 범위 유지.
- 절 번호가 없는 표현(`시편 23편`)은 자동 링크하지 않고 "확인 필요한 성경구절"로 남긴다.
- 추출은 `scripts/extract_bible_refs.py`가 결정론적으로 수행한다. Claude가 임의로 링크를 만들지 않는다.

## 제공 스크립트

- `scripts/paths.py` — config·작업파일 경로 확인 (`--ensure`로 폴더 생성). 모든 단계의 경로 출처
- `scripts/config_loader.py` — config 계약 로드·검증 (없는 키는 기본값으로 자동 보충)
- `scripts/setup_profile.py` — 터미널 대화형 설정 위저드 (보조)
- `scripts/find_sources.py` — 컴퓨터에서 볼트·설교 원고 폴더 찾기 (클라우드 포함)
- `scripts/suggest_folders.py` — 볼트를 읽어 저장 폴더·분류 정본·설교 템플릿 후보 제시
- `scripts/find_word_template.py` — 옵시디언 템플릿 폴더 설정·900번대 세팅 폴더에서 분류 정본 찾기
- `scripts/guess_naming.py` — 설교 구분·날짜·파일명 규칙 추론
- `scripts/parse_word_source.py` — 목사님 분류 노트를 읽어 허용 목록 추출 (`--sermon-only`로 설교용 부분집합, `--explain`으로 계약 확인)
- `scripts/ensure_tools.py` — 형식별 변환 도구 점검·격리 설치 (`--check` / `--install`)
- `scripts/list_fragments.py` — 기존 조각 제목 목록 / `--match-file`로 제목 초안별 근접 후보만 반환 (조각 재활용·병합의 전제)
- `scripts/scan_inputs.py` — 입력 파일/폴더 스캔 (형식별 집계·건너뛴 이유·도구 필요 여부)
- `scripts/extract_text.py` — `.docx`(pandoc→python-docx) / `.pdf`(pdftotext→pypdf) / `.hwpx`(표준 라이브러리) / `.hwp`(pyhwp) / `.md` / `.txt` 텍스트 추출 (내용 해시 캐시 — 같은 원고를 다시 변환하지 않음)
- `scripts/extract_bible_refs.py` — 성경구절 추출·정규화·wikilink 생성
- `scripts/extract_meta.py` — 날짜·제목·본문·sermon_id 추출
- `scripts/build_notes.py` — dry-run 계획 / `--write --approve WRITE`일 때만 실제 생성. 청크 폴더 입력·`--resume`(이미 편입한 원고 건너뛰기)·`--skip-conflicts`(승인 후 충돌만 건너뛰기) 지원
- `scripts/verify_output.py` — manifest 기반 출력 검증
