# pastor-skills

목회자를 위한 Claude Code 스킬입니다. 설교를 Obsidian에 정리하고, 설교 준비를 돕습니다.

## 설치하기

Claude Code를 열고 **이 주소를 붙여넣고 "이거 설치해 줘"** 라고 하시면 됩니다.

```text
https://github.com/ai4pastor/pastor-skills-dist
```

Claude가 알아서 설치해 드립니다. 명령어를 외우실 필요 없습니다.

<details>
<summary>직접 명령을 입력하고 싶으신 경우</summary>

```text
/plugin marketplace add ai4pastor/pastor-skills-dist
```

```text
/plugin install pastor-skills@ai4pastor
```

</details>

설치가 끝나면 `/` 를 입력했을 때 목록에 `pastor-skills:pastor-sermon-basic` 이 보입니다.

## 무엇이 설치되나요

| 스킬 | 하는 일 |
|---|---|
| `pastor-sermon-basic` | **여기서 시작하세요.** 폴더 위치 몇 개만 답하면 설교를 Obsidian 노트로 정리합니다. 파일명 규칙은 목사님 파일을 읽어 알아서 맞춥니다. |
| `pastor-sermon-import` | 같은 일을 하지만 형식·병합·검증 규칙을 직접 정하실 수 있습니다. 설정은 basic과 호환됩니다. |
| `pastor-sermon-lab` | 본문 연구 노트, 설교 초안 진단, 완성 설교 보강 자료를 만듭니다. |

설교 한 편에서 만들어지는 것 — 원본이 그대로 보존된 메인 노트 1개,
논지·해석·예화·적용 단위로 나뉜 설교 조각 노트 여러 개(예화는 `💡` 표시),
그리고 설교에 나온 모든 성경구절 링크(`[[요3_16]]`).

## 쓰는 법

설치 후 Claude Code에 이렇게 말씀하시면 됩니다.

```text
설교 정리해줘
```

처음 한 번은 폴더 위치 다섯 가지를 물어봅니다 — 볼트 위치, 설교 원고 위치,
정리된 노트를 넣을 폴더, 조각을 넣을 폴더, 분류를 쓰는지.
**파일명 규칙은 여쭤보지 않습니다.** 목사님 설교 파일을 먼저 읽어 보고
"이렇게 읽었습니다, 맞습니까?" 하고 확인만 받습니다.

## 안심하셔도 되는 것

- 원본 설교 파일을 수정·이동·삭제하지 않습니다.
- 이미 있는 노트를 덮어쓰지 않습니다. 같은 이름이 있으면 멈추고 물어봅니다.
- 노트를 만들기 전에 항상 미리보기를 보여주고 승인을 받습니다.
- 대량 정리가 중간에 끊겨도 처음부터 다시 하지 않습니다 — 이어서 정리합니다.

## 나만의 스킬처럼 쓰기

조각 노트의 문체나 구성이 취향과 다르면 Claude에게 이렇게 말씀해 보세요.

```text
설교 조각 문체를 바꾸고 싶어. 글머리를 더 길게 풀어 쓰고, 조각마다 요약 한 줄을 맨 위에 넣어줘.
```

Claude가 **나만의 규칙 파일**(`~/.pastor-sermon-import/custom_rules.md`)을 만들어 드립니다.
이후 모든 정리에 그 규칙이 우선 적용되고, **플러그인을 업데이트해도 그대로 유지됩니다.**
스킬 파일을 직접 고치실 필요가 없습니다 (직접 고치면 업데이트 때 사라집니다).

자세한 사용법은 각 스킬 폴더의 `INSTALL.md` 를 보세요.

## 업데이트

Claude에게 "pastor-skills 업데이트해 줘" 라고 하시거나, 직접 입력하셔도 됩니다.

```text
/plugin marketplace update ai4pastor
/plugin update pastor-skills@ai4pastor
```

매번 입력하기 번거로우시면 한 번만 켜 두세요 — 이후 새 버전이 자동으로 반영됩니다:
`/plugin` 입력 → Marketplaces 탭 → `ai4pastor` 선택 → **Enable auto-update**.

설정 파일(`~/.pastor-sermon-import/config.json`)은 업데이트해도 그대로 유지됩니다.

## 라이선스

MIT — 목사님 환경에 맞게 고쳐 쓰셔도 됩니다.

---

<!-- 아래는 이 리포를 읽는 Claude 를 위한 설치 절차입니다. -->

## 🤖 Claude 에게 — 설치를 요청받았을 때

사용자가 이 리포 주소와 함께 "설치해 줘" 라고 했다면 아래 순서로 진행하세요.
사용자는 목회자이고 터미널에 익숙하지 않을 수 있습니다. 한국어로 안내하세요.

**1단계 — 플러그인 설치를 안내한다 (권장 경로)**

슬래시 명령은 사용자가 직접 입력해야 합니다. 대신 실행할 수 없으므로,
아래 두 줄을 **한 번에 하나씩** 보여주고 입력을 요청하세요.

```text
/plugin marketplace add ai4pastor/pastor-skills-dist
```

```text
/plugin install pastor-skills@ai4pastor
```

그다음 `/` 를 입력해 목록에 `pastor-skills:pastor-sermon-basic` 이 보이는지
확인하도록 안내하세요.

**2단계 — 위 방법이 안 될 때만 직접 설치한다**

사용자가 명령 입력을 어려워하거나, 회사·학교 네트워크로 플러그인 설치가
실패하면 아래를 실행하세요. 실행 전 무엇을 하는지 한 줄로 설명하고 승인을 받으세요.

```bash
TMP=$(mktemp -d)
git clone --depth 1 https://github.com/ai4pastor/pastor-skills-dist "$TMP/pastor-skills"
mkdir -p ~/.claude/skills
cp -R "$TMP/pastor-skills/skills/." ~/.claude/skills/
ls ~/.claude/skills/ | grep pastor-sermon
```

세 폴더(`pastor-sermon-basic`, `pastor-sermon-import`, `pastor-sermon-lab`)가
보이면 설치된 것입니다. Claude Code를 다시 시작하면 스킬 목록에 나타납니다.

**주의: 1단계와 2단계를 모두 하지 마세요.** 같은 스킬이 두 개로 보입니다.
2단계로 설치했다가 나중에 플러그인으로 바꾸시려면 `~/.claude/skills/pastor-sermon-*`
폴더를 먼저 정리해야 합니다. 설정 파일(`~/.pastor-sermon-import/`)은 지우지 마세요.

**3단계 — 설치 후**

`pastor-sermon-basic` 으로 시작하도록 안내하세요. 사용자가 "설교 정리해줘" 라고
말하면 그 스킬이 폴더 위치를 물어보며 설정을 시작합니다.

`.docx` 설교 파일을 쓰는 사용자에게는 pandoc이 필요합니다
(macOS `brew install pandoc` / Windows `winget install --id JohnMacFarlane.Pandoc`).
설치가 어려우면 워드에서 `.txt` 로 저장해도 된다고 알려 주세요.
