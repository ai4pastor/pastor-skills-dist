# Bible Reference Prompt

설교 본문에 등장하는 성경구절을 추출하고 목사님 설정에 맞는 wikilink 후보로 변환한다.

## 원칙

- 약어와 풀어쓴 책 이름을 모두 인식한다.
- 장절이 명확하지 않은 표현은 `ambiguous`로 표시한다.
- 범위 처리 방식은 config의 `bible.range_policy`를 따른다.
- link_style은 config의 `bible.link_style`을 따른다.

## 출력 형식

```yaml
bible_refs:
  - raw: "요한복음 3:16"
    normalized: "요3_16"
    link: "[[요3_16]]"
    status: "ok"
  - raw: "시편 23편"
    normalized: ""
    link: ""
    status: "ambiguous"
    note: "절 번호 없음"
```
