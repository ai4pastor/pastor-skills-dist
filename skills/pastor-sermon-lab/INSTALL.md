# pastor-sermon-lab 설치 안내

설교 연구자료를 만들고, 설교 초안을 진단하고, 완성 설교에 보강거리를 제안하는
Claude Code 스킬입니다. **설치만 하면 바로 쓸 수 있습니다 — 설정 과정이 없습니다.**
설치와 사용 모두 목사님의 파일을 지우거나 고치지 않습니다.

## 설치 (명령 두 줄)

Claude Code를 열고 그대로 입력해 주세요.

```text
/plugin marketplace add ai4pastor/pastor-skills-dist
```

```text
/plugin install pastor-skills@ai4pastor
```

설치가 끝나면 `/`를 입력했을 때 목록에 `pastor-skills:pastor-sermon-lab`이 보입니다.
같은 명령으로 설교 정리 스킬(`pastor-sermon-import`)도 함께 설치됩니다.

> **예전에 zip으로 설치하셨던 분**
> `~/.claude/skills/pastor-sermon-lab/` 폴더를 지워 주세요. 그대로 두면 같은 스킬이 두 개로 보입니다.
> 기억해 둔 vault 위치(`~/.pastor-sermon-lab/`)는 **지우지 마세요** — 그대로 계속 쓰입니다.

## 업데이트

```text
/plugin marketplace update ai4pastor
```

```text
/plugin update pastor-skills@ai4pastor
```

## 준비물

1. **Claude Code**
2. `.docx` 설교 파일을 쓰신다면 다음 중 하나가 필요합니다:
   - macOS: `brew install pandoc` (권장)
   - Windows: `winget install --id JohnMacFarlane.Pandoc`
   - 또는: `pip3 install python-docx`
   - `.md`/`.txt`만 쓰시거나 본문을 붙여넣어 쓰신다면 필요 없습니다.

## 플러그인 설치가 안 될 때 (zip 방식)

회사·학교 네트워크에서 GitHub이 막혀 있으면 실패할 수 있습니다.
그때는 받으신 zip 파일의 압축을 풀어 `pastor-sermon-lab` 폴더를
`~/.claude/skills/` 아래에 넣어 주세요.
폴더 안에 `SKILL.md` 파일이 바로 보이면 올바르게 설치된 것입니다.

## 사용 — 그냥 말하면 됩니다

Claude Code를 열고:

- **연구**: "히브리서 11장 1-6절 연구해줘"
- **진단**: "이 설교 초안 진단해줘" (+ 파일 경로나 본문 붙여넣기)
- **보강**: "이 완성 설교 보강해줘"

Claude가 문서를 만들어 보여준 뒤 **"어느 폴더에 저장할까요?"** 하고 물어봅니다.
폴더를 답하시면 Obsidian vault에 노트로 저장됩니다.

- 맨 처음 한 번만 vault 위치를 물어봅니다. 그다음부터는 기억합니다.
- 지난번에 쓴 폴더를 기본값으로 제안하니, 같은 곳이면 "응"만 하시면 됩니다.
- 진단 때는 "회중이 주로 어떤 분들이세요?" 한 가지를 물어봅니다 (역시 기억합니다).

## 등급 읽는 법

연구·보강 자료의 사실 문장 끝에 붙는 표시입니다:

- ✅ 확인됨 — 독립된 출처 2곳 이상에서 교차확인
- 🟡 개연 — 학계 다수설이지만 이번에 웹으로 확인하지는 않음
- ⚠️ 논쟁중 — 학자들 사이에 견해가 갈림 (양쪽을 함께 표기)
- ❓ 불확실 — 근거가 부족함
- 🚫 사용금지 — 위조이거나 확인 실패 (설교에 인용하지 마세요)

## 안심하셔도 되는 것

- 원본 설교 파일은 절대 수정·이동·삭제되지 않습니다.
- 이미 있는 노트는 절대 덮어쓰지 않습니다. 같은 이름이 있으면 멈추고 알려드립니다.
- 설교문과 회중 이야기는 목사님 컴퓨터 밖으로 나가지 않습니다 —
  웹 검색에는 사실 확인용 키워드만 사용합니다.
