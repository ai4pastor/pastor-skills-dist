# pastor-skills

목회자를 위한 Claude Code 스킬 묶음입니다.

| 스킬 | 하는 일 |
|---|---|
| `pastor-sermon-basic` | **여기서 시작하세요.** 폴더 위치 몇 개만 답하면 설교를 Obsidian 노트로 정리합니다. 파일명 규칙은 목사님 파일을 읽어 알아서 맞춥니다. |
| `pastor-sermon-import` | 같은 일을 하지만 형식·병합·검증 규칙을 직접 정하실 수 있습니다. 설정은 basic 과 호환됩니다. |
| `pastor-sermon-lab` | 본문 연구 노트, 설교 초안 진단, 완성 설교 보강 자료를 만듭니다. |

설교 한 편에서 만들어지는 것 — 원본이 그대로 보존된 메인 노트 1개,
논지·해석·예화·적용 단위로 나뉜 설교 조각 노트 여러 개(예화는 `💡` 표시),
그리고 설교에 나온 모든 성경구절 링크(`[[요3_16]]`).

## 설치

Claude Code 에서 아래 두 줄을 입력하세요.

```text
/plugin marketplace add ai4pastor/pastor-skills-dist
```

```text
/plugin install pastor-skills@ai4pastor
```

## 업데이트

```text
/plugin marketplace update ai4pastor
/plugin update pastor-skills@ai4pastor
```

설정 파일(`~/.pastor-sermon-import/config.json`)은 업데이트해도 그대로 유지됩니다.

## 안심하셔도 되는 것

- 원본 설교 파일을 수정·이동·삭제하지 않습니다.
- 이미 있는 노트를 덮어쓰지 않습니다.
- 노트를 만들기 전에 항상 미리보기를 보여주고 승인을 받습니다.

자세한 사용법은 각 스킬 폴더의 `INSTALL.md` 를 보세요.

## 라이선스

MIT — 목사님 환경에 맞게 고쳐 쓰셔도 됩니다.
