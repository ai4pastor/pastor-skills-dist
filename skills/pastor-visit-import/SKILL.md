---
name: pastor-visit-import
description: 목사님이 이미 쓰고 계신 심방 노트·성도 노트를 지우거나 다시 쓰지 않고, 옵시디언 플러그인 a4p-pastoral-visit 가 읽는 형식(심방일지 7개 헤딩, 프론트매터 type·성도·날짜, 성도 노트의 심방 기록·임베드 섹션)으로 정리한다. 기존 헤딩은 동의어 표로 자동 매핑하고, 자유 형식 노트는 Claude 가 줄 단위 매핑 계획만 세워 스크립트가 적용한다. 진단 → 계획 → 미리보기 → 승인 → 적용 → 성도 노트 소급 반영 → 검증 → 플러그인 설정값 안내. 다음 요청에 사용 — "심방 노트 플러그인 형식으로 바꿔줘", "심방일지 정리해줘", "성도 노트 변환", "심방 기록을 플러그인에 연결해줘", "/pastor-visit-import".
---

# pastor-visit-import — 쓰던 심방 노트 그대로, 플러그인이 읽게

목사님이 지금까지 적어 오신 심방 기록을 **한 줄도 지우지 않고** a4p-pastoral-visit 플러그인이 알아보는 모양으로
다듬어 드립니다. 플러그인이 보는 것은 세 가지뿐입니다 — 프론트매터의 `type`·`성도`·`날짜`, 본문의 헤딩 이름,
성도 노트의 두 섹션. 그 세 가지만 채우고 나머지는 원문 그대로 둡니다.

- 기존 노트는 **덮어쓰지 않습니다.** 헤딩 이름을 바꾸거나(`### 대화내용` → `## 📝 대화내용`) 프론트매터 키를 **더하기만** 합니다.
- 모든 쓰기는 **미리보기(diff) → 목사님 승인 → `--write --approve WRITE`** 두 단계를 거칩니다. 승인 없이는 스크립트가 거부합니다.
- 쓰기 전 원본은 설정 홈의 **백업** 폴더(볼트 밖)에 복사되고 `--restore` 로 되돌릴 수 있습니다.
- 어떤 줄이라도 사라지거나 바뀌면 스크립트가 그 노트를 `blocked` 로 멈춥니다(원문 보존 어설션).

명령은 모두 이 스킬 폴더에서 실행한다. 윈도우에서 `python3` 가 없다고 하면 `py -3` 로 바꿔 실행한다.

## 핵심 원칙 (절대 위반 금지)

1. 노트를 삭제·이동·이름 변경하지 않는다. 파일명 바꾸기는 이 판에서 하지 않는다(플러그인은 파일명과 무관하게 `type`·`성도` 로 찾는다).
2. 기존 프론트매터 값은 바꾸지 않는다. 없는 키만 더한다. `type` 이 이미 다른 값이면 **보류**하고 목사님께 여쭌다.
3. 본문 문장은 한 글자도 고치지 않는다. 허용되는 변경은 ① 헤딩 텍스트 교정 ② 줄을 다른 헤딩 아래로 옮기기(원문 그대로) ③ 빈 섹션·프론트매터 키 추가뿐이다.
4. 자유 형식 노트의 매핑은 Claude 가 **줄 번호 기반 JSON** 으로만 제안한다. 문장을 다시 쓰거나 요약해 넣지 않는다.
5. 성도 이름이 하나로 정해지지 않으면(동명이인·추정 불가) 지어내지 않고 보류한다.
6. 작업 파일(audit.json·plan.json)에는 교인 이름이 들어간다. 설정 홈 밖으로 옮기지 않고, 끝나면 정리를 권한다.

## Step 0. 경로 확인·온보딩 (처음 한 번)

```bash
python3 scripts/visit_env.py --ensure
```

`config_exists: false` 면 `prompts/onboarding.md` 로 한 번에 한 질문씩 — 볼트 위치(`vault_hint` 가 있으면 그것을 먼저 제안),
심방 노트가 있는 폴더, 성도 노트 폴더. 모르시면 Step 1 을 폴더 없이 돌려 후보 폴더를 보여 드린다.
답을 받으면 저장한다:

```bash
python3 scripts/visit_env.py --save "vault=<볼트 경로>" "member_folder=<성도 폴더>" "visit_folder=<심방 폴더>"
```

`rules_exists: true` 면 `<설정 홈>/visit_rules.md` (**나만의 규칙**)를 읽는다 — 목사님이 쓰시는 헤딩 이름을
동의어로 추가해 둔 파일이다(아래 "개인화"). 이후 모든 단계의 `--rules` 로 넘긴다.

## Step 1. 진단 (읽기 전용)

```bash
python3 scripts/audit_visits.py --vault "<볼트>" --folder "<심방 폴더>" --folder "<성도 폴더>" --out "<work>/audit.json" --table
```

`<work>` 는 Step 0 출력의 `work`. 표를 그대로 보여 드린다 — 노트별 역할(심방일지·성도 노트·혼합·무관), 형식
(`template1` 예전 템플릿 / `seven` 7섹션 / `freeform` 자유형 / `converted` 이미 변환됨), 추정한 성도·날짜·유형.
추정이 틀린 줄이 있으면 여기서 바로잡는다(목사님 답을 Step 2 의 LLM 계획에 반영).

## Step 2. 계획

```bash
python3 scripts/plan_visits.py --audit "<work>/audit.json" --member-folder "<성도 폴더>" --visit-folder "<심방 폴더>" \
  --out "<work>/plan.json" [--rules "<홈>/visit_rules.md"] --table
```

- 템플릿형·7섹션형은 동의어 표(`data/heading_synonyms.json`)만으로 계획이 끝난다.
- `needs_llm` 에 자유형 노트가 나오면 **그 노트들만** 읽고 `prompts/classify_freeform.md` 대로 `<work>/llm_plan.json` 을 쓴 뒤
  같은 명령에 `--merge "<work>/llm_plan.json"` 을 붙여 다시 돌린다. 스크립트가 sha1·줄 번호·첫 줄 텍스트를 대조해 맞지 않는 항목은 버린다.
- `혼합 노트`(성도 노트 한 장에 여러 날짜의 심방이 들어 있는 경우)는 이 판에서 손대지 않고 알려만 드린다.

## Step 3. 미리보기

```bash
python3 scripts/apply_plan.py --plan "<work>/plan.json"
```

노트별 diff 를 `[추가]`(프론트매터 키·빈 섹션) `[교정]`(헤딩 이름) `[이동]`(줄 위치) `[보류]` 로 묶어 보여 드린다.
목사님께 여쭙는 단위 — **[추가]는 전체 한 번, [교정]은 "헤딩 교정 N건" 한 번, [이동]은 노트마다.** [보류]는 실행하지 않는다.
diff 가 길면 `--only "<경로 일부>"` 로 한 노트씩, `--quiet-diff` 로 요약만.

## Step 4. 적용

```bash
python3 scripts/apply_plan.py --plan "<work>/plan.json" --write --approve WRITE
```

끝나면 백업 폴더와 되돌리기 명령(`--restore <시각> --approve WRITE`)을 그대로 알려 드린다. `blocked` 가 있으면 사유를 보고하고 그 노트는 건너뛴다.

## Step 5. 성도 노트 소급 반영

```bash
python3 scripts/backfill_members.py --vault "<볼트>" --member-folder "<성도 폴더>" --visit-folder "<심방 폴더>" [--create-missing]
python3 scripts/backfill_members.py ... --write --approve WRITE
```

일지마다 성도 노트의 `## 📝 심방 기록` 에 한 줄, `## 📌 중요 심방 내용 (임베드)` 에 임베드 3줄을 붙이고 일지에 `반영: true` 를 적는다
— 플러그인의 '반영' 과 글자까지 같은 결과라 플러그인이 "이미 반영됨"으로 인식한다. 성도 노트가 없는 분은 `--create-missing` 을 여쭤본 뒤에만
최소 노트(이름·심방상태만)로 만든다. 성도 노트의 기존 내용은 그대로 두고 섹션을 끝에 붙인다.

## Step 6. 검증 → 플러그인 설정

```bash
python3 scripts/verify_visits.py --vault "<볼트>" --member-folder "<성도 폴더>" --visit-folder "<심방 폴더>"
```

노트별 헤딩 커버리지(n/7)·성도 링크·반영 여부를 표로 보여 주고, 마지막에 **플러그인 설정에 붙여넣을 값**(성도 노트 폴더 / 심방일지 폴더)을 찍는다.
목사님께 안내: 설정 → a4p-pastoral-visit → 두 폴더 입력 → [검증] → 왼쪽 리본 심방 아이콘으로 대시보드. 플러그인 설치는 `references/plugin_setup.md`.
비표준 심방 유형(예: 축하심방)이 있으면 플러그인 설정의 '심방 유형' 목록에 추가하라고 함께 알린다.

## 개인화 — 두 길

1. **나만의 규칙** `<설정 홈>/visit_rules.md` — 업데이트해도 남는다. 헤딩 동의어를 이렇게 적는다:
   ```markdown
   - 대화내용: 나눈 말씀, 심방 나눔
   - 기도제목: 기도 부탁, 중보
   - 후속조치: 다음에 할 일
   ```
2. 스킬 폴더를 복사해 자기 이름으로 고치기 — 자유롭지만 **업데이트를 받지 못한다.**

## 제공 파일

- `scripts/visit_env.py` — 설정 홈·작업·백업 경로, 설정 저장
- `scripts/audit_visits.py` — 1단계 진단 (읽기 전용)
- `scripts/plan_visits.py` — 2단계 계획 (+ `--merge` LLM 계획, `--rules` 동의어)
- `scripts/apply_plan.py` — 3·4단계 dry-run / `--write --approve WRITE` / `--restore`
- `scripts/backfill_members.py` — 5단계 성도 노트 소급 반영 (플러그인 planSync 와 바이트 호환)
- `scripts/verify_visits.py` — 6단계 검증 + 설정값
- `scripts/visit_lib.py` — 공용(플러그인 로직 포트), `scripts/config_loader.py` — 설정 홈(공유)
- `prompts/onboarding.md`, `prompts/classify_freeform.md`, `data/heading_synonyms.json`
- `references/target_format.md`(플러그인이 읽는 형식 정본), `references/plugin_setup.md`(플러그인 설치)
- `INSTALL.md` — 목사님께 드리는 설치·사용 안내

## 윈도우에서

- 경로는 `C:/Users/이름/...` 처럼 슬래시로 적는 것이 안전하다. `python3` 가 없으면 `py -3`.
- 스크립트는 표준 라이브러리만 쓰고 파일을 UTF-8 로 읽고 쓴다. 한글 사용자 이름 폴더도 된다.
