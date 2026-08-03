---
name: pastor-sermon-lab
description: 설교 준비를 돕는 통합 스킬. 3개 모드 — 연구(본문·주제 연구노트, 웹 교차검증 + 신뢰 등급), 진단(설교 초안에 회중 관점 피드백 + 6차원 진단), 보강(완성 설교에 추가 자료·다른 관점 제안, 재작성 안 함). 결과는 목사님께 폴더를 여쭤보고 Obsidian vault에 노트로 저장. 설정 과정 없음. 트리거 — "본문 연구해줘", "설교 진단해줘", "설교 피드백", "설교 보강해줘".
---

# pastor-sermon-lab

목사님의 설교 준비를 돕는 설교 연구실이다. 별도 설정 없이 바로 쓴다:
요청 → 문서 생성 → 미리보기 → "어느 폴더에 넣을까요?" → Obsidian에 저장.

## 핵심 원칙 (절대 위반 금지)

1. 설교 원본 파일은 절대 수정·이동·삭제하지 않는다.
2. 기존 Obsidian 노트는 절대 덮어쓰지 않는다. 같은 이름이 있으면 멈추고 알린다.
3. 저장 전 항상 노트 내용을 보여주고, 저장 폴더를 목사님께 확인받는다.
4. **근거 없는 사실 주장 금지.** 모든 사실 진술에는 신뢰 등급(✅🟡⚠️❓🚫)을 붙인다.
   등급은 선언이 아니라 증거에서 나온다 — 규칙은 `references/grade_rules.md`.
5. 신학적 해석·적용 제안은 등급 대상이 아니다. 해당 섹션에 `(해석)` 표시만 한다.
6. 설교문 문장·교인 정보·목사님 개인 정보를 웹 검색 질의에 넣지 않는다.
7. frontmatter는 YAML 표준 파서로 다루지 않는다 — 스크립트가 생성하는 형식을 그대로 쓴다.
8. 출력은 지시가 아니라 제안의 언어로 쓴다. 설교의 주인은 목사님이다.

## 모드

| 모드 | 트리거 예 | 입력 | 로드할 프롬프트 |
|---|---|---|---|
| 연구 | "요한복음 1장 연구해줘" | 본문/주제 | `prompts/research.md` + `references/research_outline.md` + `references/method_guide.md` |
| 진단 | "이 설교 초안 진단해줘" | 설교 초안 | `prompts/diagnose.md` |
| 보강 | "이 완성 설교 보강해줘" | 완성 설교 | `prompts/enrich.md` |

- 초안인지 완성본인지 모호하면 목사님께 물어본다 (진단 vs 보강 분기).
- 모드 프롬프트는 해당 모드를 실행할 때만 읽는다.
- 연구 분량은 3단계(간단/표준/상세, 기본 표준) — 세부는 `prompts/research.md`.

## 흐름 (모든 모드 동일)

### Step 1. 입력 확보

- 파일 입력(.docx/.md/.txt)이면: `python3 scripts/extract_text.py "{파일 경로}"`
- 본문·주제·붙여넣은 텍스트면 그대로 사용한다. 원본 파일은 읽기 전용이다.

### Step 2. 생성 (LLM 분석)

`prompts/{mode}.md`의 규칙을 따른다. 사실 주장이 있는 모드(연구·보강)는
`prompts/verify_facts.md`의 웹 교차검증을 함께 수행한다.
결과를 `~/.pastor-sermon-lab/work/{mode}.json`에 저장한다.

### Step 3. 결정론 게이트 (조용히 수행)

```bash
python3 scripts/verify_claims.py ~/.pastor-sermon-lab/work/claims.json          # 연구·보강만
python3 scripts/verify_note.py --result ~/.pastor-sermon-lab/work/{mode}.json --mode {mode}
```

실패하면 지적된 항목을 수정하고 재실행한다. `prompts/self_check.md`로 자기 점검까지
마친 뒤에만 다음 단계로 간다. 이 과정을 목사님께 장황하게 설명하지 않는다.

### Step 4. 미리보기 + 저장 위치 질문

노트 내용을 보여준 뒤 저장 위치를 여쭤본다:

```bash
python3 scripts/config_loader.py    # 기억된 vault·지난번 폴더 확인
```

- vault가 비어 있으면 (첫 사용): "Obsidian vault 폴더가 어디인가요?" →
  `python3 scripts/config_loader.py --remember-vault "{경로}"`로 기억한다.
- 폴더 질문: "어느 폴더에 저장할까요?" — 지난번 같은 모드에 쓴 폴더가 있으면
  그것을 기본값으로 제안하고, vault의 실제 폴더 몇 개를 후보로 보여준다 (`ls`로 확인).

### Step 5. 저장

목사님이 폴더를 확정하면:

```bash
python3 scripts/build_note.py --mode {mode} --result ~/.pastor-sermon-lab/work/{mode}.json \
  --folder "{확정된 폴더}" --write --approve WRITE
python3 scripts/config_loader.py --remember-folder {mode} "{확정된 폴더}"
```

같은 이름의 노트가 이미 있으면 저장이 차단된다 — 목사님께 알리고 제목을 바꿔 재시도한다.

### Step 6. 검증 후 보고

```bash
python3 scripts/verify_output.py "{manifest 경로}"
```

`blocked`면 보고 전에 수정한다. 보고는 짧게: 저장된 노트 경로, 등급 분포(연구·보강),
점수·약점(진단), 경고 사항.

## 신뢰 등급 (요약)

`✅확인됨 / 🟡개연 / ⚠️논쟁중 / ❓불확실 / 🚫사용금지` — 부여·승격·강등 규칙과
표기법은 `references/grade_rules.md`에만 정의되어 있다. 임의 변형 금지.

## 제공 스크립트

- `scripts/config_loader.py` — vault·폴더·회중 기억 (memory.json, 자동 관리)
- `scripts/extract_text.py` — `.docx`/`.md`/`.txt` 텍스트 추출
- `scripts/extract_bible_refs.py` — 성경구절 추출·정규화·wikilink 생성
- `scripts/build_note.py` — 노트 생성 (dry-run 기본, `--write --approve WRITE`일 때만 쓰기)
- `scripts/verify_claims.py` — 주장 원장 등급-증거 정합 게이트
- `scripts/verify_note.py` — 등급 커버리지·관찰 구역 위반·금지어·성경 장 범위 검사
- `scripts/verify_output.py` — 저장 후 검증
