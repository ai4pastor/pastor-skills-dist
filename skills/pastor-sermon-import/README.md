# pastor-sermon-import

목회자 개인의 설교 자료를 Obsidian vault에 자동 정리하는 배포형 Claude Code 스킬입니다.

## 산출물

설교 원본 파일(.docx/.md/.txt)을 읽어 다음을 생성합니다.

- 메인 설교 노트 (frontmatter 분류 + `## [[조각]]` 링크 + 원본 설교문 보존)
- 의미 단위로 분해된 설교 조각 노트 N개 (조각별 doctrine/tags)
- 성경구절 wikilink (`[[요3_16]]` 표준, 66권 약어·풀어쓴 이름 인식)
- dry-run 미리보기와 검증 리포트

## 구성

- `SKILL.md` — 스킬 본문 (Claude Code 워크플로우)
- `INSTALL.md` — 수강생용 설치 안내
- `prompts/` — 온보딩·조각 분해·WORD 분류·성경구절 프롬프트
- `scripts/` — 결정론 처리 스크립트 (추출·계획·쓰기·검증)
- `examples/config.example.json` — 설정 예시

## 설계 원칙

- 원본 파일 보존, 기존 노트 덮어쓰기 금지, dry-run 후 승인
- 개인 경로·분류값은 config 분리 (`~/.pastor-sermon-import/config.json`)
- WORD/doctrine은 config 허용 목록 안에서만 — 스크립트가 목록 밖 값을 걸러냄
- 조각 분해·분류는 Claude(LLM)가 수행하고, 파일 생성·검증은 스크립트가 결정론적으로 수행
- LLM 분석이 없으면 결정론 분해로 fallback

## 테스트

모노레포 루트에서:

```bash
bash tests/pastor-sermon-import/run_smoke.sh
python3 tests/pastor-sermon-import/run_write_smoke.py
python3 tests/pastor-sermon-import/run_injection_smoke.py
```

기대 결과: `dry-run assertions OK`, `bible assertions OK`, `verify: ok`, `injection assertions OK`

## 배포

```bash
python3 tools/build_release.py pastor-sermon-import --version v1.0
```

`dist/pastor-sermon-import-v1.0.zip` 생성 → 수강생은 압축 해제 후 `~/.claude/skills/`에 폴더째 복사.

## 남은 로드맵

1. 실제 목사님 vault 유사 샘플 4종 검증 (단순 구조 / WORD 사용 / 성경노트 보유 / 충돌 존재)
2. 기존 조각 노트와의 병합 정책 (동일 제목 메모에 글머리 추가)
3. PDF·HWP/HWPX 입력 지원
4. 대량 import resume·중복 설교 감지
