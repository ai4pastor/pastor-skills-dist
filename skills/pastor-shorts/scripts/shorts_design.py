"""쇼츠 디자인 시안 4종 — 위·아래 틀, 영상 창, 자막 스타일 (출력 1080x1920 고정).

시안마다 레이어 세트를 돌려준다:
    bg     움직이지 않는 배경 (없으면 None)
    under  흐린 배경 위·영상 창 아래에 깔리는 층 (말씀 카드의 색조·그림자)
    over   제목·한 줄 요약·본문·설교자 등 위에 얹는 층 (투명 배경)
    win    영상 창 위치·크기·모서리 (None 이면 화면 가득)
    cap    자막 스타일 (글꼴·크기·색·강조색·위치·최대 폭)

핵심 정보는 유튜브 쇼츠 화면 요소가 덮는 자리를 피한다 (대략값):
    위 0~6%(검색·카메라 아이콘) · 오른쪽 x>86% & y 45~82%(좋아요·댓글 버튼) · 아래 82~100%(채널명·제목)
"""
from __future__ import annotations

from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import shorts_env as env

W, H = 1080, 1920
SAFE = {"top": 0.06, "rail_x": 0.86, "rail_y": (0.45, 0.82), "bottom": 0.82}

FONT_FILES = {
    "serif_xb": "NanumMyeongjo-ExtraBold.ttf",
    "serif_b": "NanumMyeongjo-Bold.ttf",
    "serif_r": "NanumMyeongjo-Regular.ttf",
    "sans_xb": "Pretendard-ExtraBold.otf",
    "sans_sb": "Pretendard-SemiBold.otf",
    "sans_m": "Pretendard-Medium.otf",
    "sans_r": "Pretendard-Regular.otf",
    "sans_l": "Pretendard-Light.otf",
    "latin": "Marcellus-Regular.ttf",
}

DESIGNS = {
    "1": ("클래식", "클래식 네이비 & 골드"),
    "2": ("아이보리", "아이보리 에디토리얼"),
    "3": ("시네마틱", "시네마틱 다크"),
    "4": ("말씀카드", "말씀 카드"),
}


def font(key: str, size: int) -> ImageFont.FreeTypeFont:
    path = Path(os.environ.get("PASTOR_SHORTS_FONTS") or env.fonts_dir()) / FONT_FILES[key]
    return ImageFont.truetype(str(path), size)


def rgba(h: str, a: int = 255) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


# ---------- 글자 도구 ----------
def tracked(d, cx, y, text, f, fill, tracking=0):
    widths = [d.textlength(c, font=f) for c in text]
    x = cx - (sum(widths) + tracking * (len(text) - 1)) / 2
    for c, w in zip(text, widths):
        d.text((x, y), c, font=f, fill=fill)
        x += w + tracking


def centered(d, cx, y, text, f, fill, shadow=None):
    w = d.textlength(text, font=f)
    if shadow:
        d.text((cx - w / 2 + 2, y + 3), text, font=f, fill=shadow)
    d.text((cx - w / 2, y), text, font=f, fill=fill)


def fit(d, text, key, size, max_w, min_size=28):
    """max_w 안에 들어가는 가장 큰 글자 크기 — 제목이 길어도 틀이 깨지지 않게."""
    while size > min_size and d.textlength(text, font=font(key, size)) > max_w:
        size -= 2
    return font(key, size)


# 줄 끝에 두면 어색한 관형사·의존명사 ("한 2년쯤", "그럴 수 있다")
LINE_END_BAD = ("한", "두", "세", "네", "첫", "수", "줄", "그", "이", "저", "몇", "약", "각", "새", "옛", "온", "총")
# 줄 첫머리에 오면 안 되는 의존명사 ("있다는 걸", "모를 때가")
BOUND_NOUNS = ("걸", "것", "거", "건", "게", "줄", "수", "때", "데", "뿐", "듯", "만큼")


def balanced_lines(d, text, f, max_w):
    """한 줄에 들어가면 한 줄, 아니면 두 줄 길이를 고르게 — 한국어 붙임 규칙을 지키며."""
    if d.textlength(text, font=f) <= max_w:
        return [text]
    words = text.split(" ")
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        wa, wb = d.textlength(a, font=f), d.textlength(b, font=f)
        bad = (len(words[i]) <= 3 and words[i].startswith(BOUND_NOUNS)) or words[i - 1] in LINE_END_BAD
        score = max(wa, wb) + (10_000 if bad else 0)
        if wa <= max_w and wb <= max_w and (best is None or score < best[0]):
            best = (score, [a, b])
    if best:
        return best[1]
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def draw_caption(base, text, highlight, cap):
    d = ImageDraw.Draw(base)
    f = font(cap["font"], cap["size"])
    lines = balanced_lines(d, text, f, cap["max_w"])
    lh = int(f.size * 1.34)
    y = cap["cy"] - lh * len(lines) / 2
    for line in lines:
        x = cap["cx"] - d.textlength(line, font=f) / 2
        for w in line.split(" "):
            fill = cap["hl"] if any(h and h in w for h in highlight) else cap["color"]
            if cap.get("shadow"):
                d.text((x + 2, y + 3), w, font=f, fill=cap["shadow"])
            d.text((x, y), w, font=f, fill=fill)
            x += d.textlength(w + " ", font=f)
        y += lh


def caption_image(text, highlight, cap):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_caption(img, text, highlight, cap)
    return img


# ---------- 장식 ----------
def vgradient(size, top, bottom):
    w, h = size
    col = Image.new("RGBA", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        col.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(4)))
    return col.resize((w, h))


def ornament_rule(d, cx, y, half, color, gap=16, r=6, width=2):
    d.line([(cx - half, y), (cx - gap, y)], fill=color, width=width)
    d.line([(cx + gap, y), (cx + half, y)], fill=color, width=width)
    d.polygon([(cx, y - r), (cx + r, y), (cx, y + r), (cx - r, y)], fill=color)


def cross(d, cx, cy, h, color, width=3):
    d.line([(cx, cy - h / 2), (cx, cy + h / 2)], fill=color, width=width)
    d.line([(cx - h * 0.32, cy - h * 0.18), (cx + h * 0.32, cy - h * 0.18)], fill=color, width=width)


def drop_shadow(base, box, radius, blur=28, offset=18, alpha=150):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    x0, y0, x1, y1 = box
    ImageDraw.Draw(layer).rounded_rectangle([x0, y0 + offset, x1, y1 + offset], radius=radius, fill=(0, 0, 0, alpha))
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def header(d, m, s):
    if s.get("label"):
        tracked(d, W / 2, s["label_y"], s["label"], font(s["label_font"], s["label_size"]), s["label_color"],
                tracking=s.get("label_tracking", 0))
    ft = fit(d, m.get("title", ""), s["title_font"], s["title_size"], 940)
    centered(d, W / 2, s["title_y"], m.get("title", ""), ft, s["title_color"], shadow=s.get("title_shadow"))
    if m.get("hook"):
        fh = fit(d, m["hook"], s["hook_font"], s["hook_size"], 920, min_size=26)
        centered(d, W / 2, s["hook_y"], m["hook"], fh, s["hook_color"])


def credit(m):
    return " · ".join(x for x in (m.get("preacher"), m.get("church")) if x)


# ---------- 시안 ----------
def design_1(m):
    gold, ivory = rgba("#C9A86A"), rgba("#F4ECDD")
    bg = vgradient((W, H), rgba("#0D1830"), rgba("#0A1326"))
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    ornament_rule(d, W / 2, 212, 190, gold)
    header(d, m, dict(label=m.get("label_en", "SUNDAY SERMON"), label_font="latin", label_size=32, label_y=146,
                      label_color=gold, label_tracking=8, title_font="serif_xb", title_size=84, title_y=244,
                      title_color=ivory, hook_font="serif_r", hook_size=38, hook_y=368,
                      hook_color=ivory[:3] + (205,)))
    win = dict(x=60, y=470, w=960, h=860, r=14)
    d.rounded_rectangle((win["x"], win["y"], win["x"] + win["w"], win["y"] + win["h"]), radius=14,
                        outline=gold, width=2)
    d.line([(500, 1488), (580, 1488)], fill=gold, width=2)
    line = "   |   ".join(x for x in (m.get("scripture"), m.get("preacher")) if x)
    centered(d, W / 2, 1502, line, font("sans_m", 30), ivory[:3] + (220,))
    if m.get("church"):
        centered(d, W / 2, 1542, m["church"], font("serif_r", 26), gold)
    cap = dict(font="sans_sb", size=50, color=ivory, hl=gold, cx=540, cy=1409, max_w=700, shadow=None)
    return dict(bg=bg, under=None, over=over, win=win, cap=cap, moving_bg=False)


def design_2(m):
    ink, warm, burgundy = rgba("#26211D"), rgba("#6E655B"), rgba("#8C2A2A")
    bg = Image.new("RGBA", (W, H), rgba("#F2ECE1"))
    noise = Image.effect_noise((W, H), 18).convert("RGBA")
    noise.putalpha(14)
    bg.alpha_composite(noise)
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    cross(d, W / 2, 150, 34, ink, width=3)
    header(d, m, dict(label=m.get("label_ko", "주일 말씀"), label_font="serif_b", label_size=30, label_y=186,
                      label_color=warm, label_tracking=16, title_font="serif_xb", title_size=88, title_y=236,
                      title_color=ink, hook_font="serif_r", hook_size=38, hook_y=358, hook_color=warm))
    win = dict(x=64, y=452, w=952, h=848, r=0)
    d.rectangle((win["x"] - 12, win["y"] - 12, win["x"] + win["w"] + 12, win["y"] + win["h"] + 12),
                outline=ink[:3] + (150,), width=2)
    d.line([(420, 1458), (660, 1458)], fill=ink[:3] + (90,), width=1)
    if m.get("scripture"):
        centered(d, W / 2, 1474, m["scripture"], font("serif_r", 32), ink)
    tracked(d, W / 2, 1520, credit(m), font("sans_m", 25), warm, tracking=2)
    d.rectangle((0, 1592, W, H), fill=rgba("#2A2521"))
    d.line([(0, 1592), (W, 1592)], fill=burgundy, width=4)
    cap = dict(font="serif_b", size=46, color=ink, hl=burgundy, cx=540, cy=1384, max_w=760, shadow=None)
    return dict(bg=bg, under=None, over=over, win=win, cap=cap, moving_bg=False)


def design_3(m):
    white, gold = rgba("#FFFFFF"), rgba("#E8C46C")
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    over.alpha_composite(vgradient((W, 640), (0, 0, 0, 235), (0, 0, 0, 0)), (0, 0))
    over.alpha_composite(vgradient((W, 860), (0, 0, 0, 0), (0, 0, 0, 240)), (0, H - 860))
    d = ImageDraw.Draw(over)
    d.line([(470, 150), (610, 150)], fill=white[:3] + (180,), width=2)
    header(d, m, dict(label=m.get("label_en", "SUNDAY SERMON"), label_font="latin", label_size=30, label_y=170,
                      label_color=white[:3] + (200,), label_tracking=10, title_font="serif_xb", title_size=82,
                      title_y=222, title_color=white, title_shadow=(0, 0, 0, 140), hook_font="sans_l",
                      hook_size=36, hook_y=342, hook_color=white[:3] + (215,)))
    if m.get("scripture"):
        centered(d, W / 2, 1466, m["scripture"], font("serif_r", 32), white[:3] + (225,))
    tracked(d, W / 2, 1512, credit(m), font("sans_r", 26), white[:3] + (170,), tracking=2)
    cap = dict(font="sans_sb", size=56, color=white, hl=gold, cx=540, cy=1300, max_w=720, shadow=(0, 0, 0, 170))
    return dict(bg=None, under=None, over=over, win=None, cap=cap, moving_bg=False)


def design_4(m):
    white, gold = rgba("#FFFFFF"), rgba("#F2C46D")
    win = dict(x=72, y=420, w=936, h=830, r=30)
    under = Image.new("RGBA", (W, H), rgba("#1B1A2C", 200))
    under.alpha_composite(vgradient((W, 520), (8, 8, 20, 170), (8, 8, 20, 0)), (0, 0))
    under.alpha_composite(vgradient((W, 560), (8, 8, 20, 0), (8, 8, 20, 200)), (0, H - 560))
    drop_shadow(under, (win["x"], win["y"], win["x"] + win["w"], win["y"] + win["h"]), 30)
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    label = "  ·  ".join(x for x in (m.get("church"), m.get("label_ko", "주일 말씀")) if x)
    header(d, m, dict(label=label, label_font="sans_m", label_size=28, label_y=148, label_color=white[:3] + (210,),
                      label_tracking=3, title_font="serif_xb", title_size=84, title_y=196, title_color=white,
                      hook_font="serif_r", hook_size=36, hook_y=316, hook_color=white[:3] + (220,)))
    pill = (150, 1412, 910, 1560)
    d.rounded_rectangle(pill, radius=26, fill=(255, 255, 255, 34), outline=(255, 255, 255, 70), width=1)
    if m.get("verse"):
        text = f"“{m['verse']}”"
        centered(d, W / 2, 1436, text, fit(d, text, "serif_r", 31, pill[2] - pill[0] - 60, min_size=22), white)
    ref = "  ·  ".join(x for x in (m.get("verse_ref") or m.get("scripture"), m.get("preacher")) if x)
    centered(d, W / 2, 1494, ref, font("sans_m", 25), gold)
    cap = dict(font="sans_sb", size=50, color=white, hl=gold, cx=540, cy=1331, max_w=720, shadow=(0, 0, 0, 150))
    return dict(bg=None, under=under, over=over, win=win, cap=cap, moving_bg=True)


BUILDERS = {"1": design_1, "2": design_2, "3": design_3, "4": design_4}


def layers(key: str, meta: dict) -> dict:
    return BUILDERS[key](meta)


# ---------- 원본 영상에서 잘라 올 영역 ----------
def even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def window_crops(src_w, src_h, win_w, win_h, focus, height_ratio=0.555, zoom_tight=1.08):
    """창 비율에 맞춘 (넓게, 살짝 확대) 두 영역 — 얼굴이 위쪽 1/3 근처에 오도록 focus 기준."""
    ar = win_w / win_h
    out = []
    for ch in (src_h * height_ratio, src_h * height_ratio / zoom_tight):
        cw = min(src_w, ch * ar)
        ch = cw / ar
        x0 = min(max(0, focus[0] - cw / 2), src_w - cw)
        y0 = min(max(0, focus[1] - ch / 2), src_h - ch)
        out.append((even(cw), even(ch), even(x0), even(y0)))
    return out


def fullbleed_crops(src_w, src_h, focus, zoom_tight=1.08):
    """화면 가득(9:16) — 원본 높이를 다 쓰고 가로는 focus 중심."""
    out = []
    for ch in (src_h, src_h / zoom_tight):
        cw = ch * 9 / 16
        x0 = min(max(0, focus[0] - cw / 2), src_w - cw)
        y0 = min(max(0, focus[1] - ch * 0.45), src_h - ch)
        out.append((even(cw), even(ch), even(x0), even(y0)))
    return out


def crop_resize(frame, box, size):
    cw, ch, x0, y0 = box
    return frame.crop((x0, y0, x0 + cw, y0 + ch)).resize(size, Image.LANCZOS)


# ---------- 미리보기 (정지 화면) ----------
def compose_still(key, frame, meta, focus, sample_caption, highlight, height_ratio=0.555):
    """영상과 같은 레이어로 정지 시안을 만든다 — 미리보기 = 실제 결과."""
    L = layers(key, meta)
    src_w, src_h = frame.size
    if L["win"]:
        win = L["win"]
        box = window_crops(src_w, src_h, win["w"], win["h"], focus, height_ratio)[0]
        video = crop_resize(frame, box, (win["w"], win["h"]))
    else:
        video = crop_resize(frame, fullbleed_crops(src_w, src_h, focus)[0], (W, H))
    if L["bg"] is not None:
        img = L["bg"].copy()
    elif L["moving_bg"]:
        img = crop_resize(frame, fullbleed_crops(src_w, src_h, focus)[0], (270, 480))
        img = img.filter(ImageFilter.GaussianBlur(11)).resize((W, H), Image.LANCZOS).convert("RGBA")
    else:
        img = video.convert("RGBA")
    if L["under"] is not None:
        img.alpha_composite(L["under"])
    if L["win"]:
        win = L["win"]
        mask = Image.new("L", (win["w"], win["h"]), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, win["w"] - 1, win["h"] - 1], radius=win["r"], fill=255)
        img.paste(video.convert("RGBA"), (win["x"], win["y"]), mask)
    img.alpha_composite(L["over"])
    img.alpha_composite(caption_image(sample_caption, highlight, L["cap"]))
    return img


def shorts_ui(img, channel="@채널이름", title="쇼츠 제목"):
    """유튜브 쇼츠 화면 요소(대략)를 덧그려 무엇이 가려지는지 보여 준다."""
    ui = img.copy()
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    wt, sh = (255, 255, 255, 235), (0, 0, 0, 120)
    for x in (900, 980, 1040):
        d.ellipse([x - 20, 42, x + 20, 82], outline=wt, width=4)
    d.line([(36, 62), (62, 40)], fill=wt, width=5)
    d.line([(36, 62), (62, 84)], fill=wt, width=5)
    fs = font("sans_m", 22)
    for i, label in enumerate(["좋아요", "싫어요", "댓글", "공유", "리믹스"]):
        cy = int(H * 0.50) + i * 128
        d.ellipse([974, cy - 36, 1046, cy + 36], fill=(255, 255, 255, 60), outline=wt, width=3)
        lw = d.textlength(label, font=fs)
        d.text((1010 - lw / 2 + 1, cy + 46), label, font=fs, fill=sh)
        d.text((1010 - lw / 2, cy + 44), label, font=fs, fill=wt)
    d.ellipse([36, 1612, 96, 1672], fill=(200, 200, 200, 255))
    d.text((112, 1622), channel, font=font("sans_sb", 30), fill=wt)
    d.rounded_rectangle([392, 1618, 492, 1668], radius=25, fill=(255, 255, 255, 240))
    d.text((414, 1626), "구독", font=font("sans_sb", 28), fill=(15, 15, 15, 255))
    d.text((36, 1700), title, font=font("sans_m", 30), fill=wt)
    d.rectangle([0, H - 120, W, H], fill=(15, 15, 15, 235))
    for i in range(5):
        cx = 108 + i * 216
        d.rounded_rectangle([cx - 22, H - 86, cx + 22, H - 46], radius=8, outline=wt, width=3)
    ui.alpha_composite(layer)
    return ui


def sheet(images, labels, path, scale=0.5):
    w, h = int(W * scale), int(H * scale)
    pad, label_h = 28, 64
    out = Image.new("RGB", (pad + len(images) * (w + pad), pad + h + label_h), (236, 233, 228))
    d = ImageDraw.Draw(out)
    f = font("sans_sb", 28)
    for i, (im, lab) in enumerate(zip(images, labels)):
        x = pad + i * (w + pad)
        out.paste(im.convert("RGB").resize((w, h), Image.LANCZOS), (x, pad))
        lw = d.textlength(lab, font=f)
        d.text((x + (w - lw) / 2, pad + h + 16), lab, font=f, fill=(40, 36, 32))
    out.save(path)
