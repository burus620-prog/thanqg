#!/usr/bin/env python3
"""캡처 검증 — 찍힌 이미지가 쓸 만한지 기계가 먼저 걸러내고, 사람이 볼 검토표를 만든다.

  python3 verify.py

스크립트가 "성공"이라고 말하는 것은 클릭에서 예외가 나지 않았다는 뜻일 뿐,
의도한 화면이 찍혔다는 뜻이 아니다. 이 도구는 그 간극을 메운다.

기계가 잡아낼 수 있는 것
  · 원본이 요구하는 이미지가 다 있는지
  · 해상도가 규칙(1920px)에 맞는지
  · 완전히 같은 이미지가 두 장 이상인지  → 화면 전환 전에 찍혔다는 뜻
  · 거의 같은 이미지인지                  → 단계별 차이가 없다는 뜻
  · 백지에 가까운 이미지인지              → 로딩 전에 찍혔다는 뜻
  · 여러 화면이 서로 똑같은지             → 로그인 화면만 반복해 찍혔을 가능성

기계가 잡아낼 수 없는 것 (review.html 에서 사람이 확인)
  · 설명 문장과 화면이 실제로 맞는지
  · 개인정보가 제대로 가려졌는지
  · 클릭이 엉뚱한 곳에 들어가 원치 않는 상태가 되지 않았는지
"""
import hashlib
import os
import sys
from pathlib import Path

import yaml

try:
    from PIL import Image
except ImportError:
    sys.exit("pip install pillow 가 필요합니다.")

BASE = Path(__file__).resolve().parent
SRC = BASE / "src"
CAPS = BASE / "captures"
EXPECT_WIDTH = 1920
FLAT_THRESHOLD = 6.0     # 표준편차가 이보다 낮으면 사실상 단색
NEAR_DUP_BITS = 4        # dhash 차이가 이 이하면 거의 같은 이미지


def expected():
    """원본 YAML이 요구하는 이미지와 그 자리의 설명 문장을 모은다."""
    want = {}
    for f in sorted(SRC.glob("*.yaml")):
        for doc in yaml.safe_load_all(open(f, encoding="utf-8")):
            for item in doc or []:
                sid = item.get("screen_id")
                if not sid:
                    continue
                groups = [(None, item.get("steps", []))]
                groups += [(sf["name"], sf["steps"]) for sf in item.get("sub_flows", [])]
                for flow, steps in groups:
                    for s in steps:
                        if s.get("image"):
                            want[s["image"]] = {
                                "screen_id": sid,
                                "screen": item.get("screen_name", sid),
                                "flow": flow,
                                "no": s.get("no"),
                                "action": str(s.get("action", "")).strip(),
                                "note": str(s.get("note") or "").strip(),
                            }
    return want


def dhash(img, size=8):
    g = img.convert("L").resize((size + 1, size))
    px = list(g.tobytes())
    bits = 0
    for r in range(size):
        for c in range(size):
            bits = (bits << 1) | (px[r * (size + 1) + c] < px[r * (size + 1) + c + 1])
    return bits


def stats(path):
    with Image.open(path) as im:
        w, h = im.size
        small = im.convert("L").resize((160, 90))
        px = list(small.tobytes())
        mean = sum(px) / len(px)
        var = sum((p - mean) ** 2 for p in px) / len(px)
        return {"w": w, "h": h, "std": var ** 0.5, "dhash": dhash(im),
                "md5": hashlib.md5(open(path, "rb").read()).hexdigest()}


def main():
    want = expected()
    found = {p.name: p for p in CAPS.rglob("*.png")}

    missing = sorted(set(want) - set(found))
    extra = sorted(set(found) - set(want))

    info = {}
    for name, path in found.items():
        if name in want:
            info[name] = stats(path)

    problems = []

    for name in missing:
        problems.append(("없음", name, "촬영되지 않았습니다"))
    for name in extra:
        problems.append(("여분", name, "원본이 요구하지 않는 이미지입니다"))

    for name, s in sorted(info.items()):
        if s["w"] != EXPECT_WIDTH:
            problems.append(("해상도", name, f"{s['w']}x{s['h']} — 규칙은 폭 {EXPECT_WIDTH}px"))
        if s["std"] < FLAT_THRESHOLD:
            problems.append(("백지", name, "화면이 거의 비어 있습니다. 로딩 전에 찍혔을 수 있습니다"))

    # 완전 중복
    by_md5 = {}
    for name, s in info.items():
        by_md5.setdefault(s["md5"], []).append(name)
    for names in by_md5.values():
        if len(names) > 1:
            group = sorted(names)
            problems.append(("완전중복", ", ".join(group),
                             "픽셀까지 같은 이미지입니다. 화면이 바뀌기 전에 연속으로 찍혔습니다"))

    # 거의 중복 (다른 화면끼리 겹치면 더 심각)
    names = sorted(info)
    seen = set()
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            if info[a]["md5"] == info[b]["md5"]:
                continue
            if bin(info[a]["dhash"] ^ info[b]["dhash"]).count("1") <= NEAR_DUP_BITS:
                key = (a, b)
                if key in seen:
                    continue
                seen.add(key)
                cross = want[a]["screen_id"] != want[b]["screen_id"]
                problems.append(("화면혼동" if cross else "거의중복", f"{a} ↔ {b}",
                                 "서로 다른 화면인데 거의 같습니다. 이동이 안 된 채 찍혔을 수 있습니다"
                                 if cross else "단계별 차이가 거의 없습니다"))

    # ---- 보고
    print(f"원본 요구 {len(want)}장 · 실제 {len(found)}장 · 검사 대상 {len(info)}장\n")
    if problems:
        w = max(len(p[0]) for p in problems)
        for kind, target, msg in problems:
            print(f"[{kind:<{w}}] {target}\n{'':>{w+3}}{msg}")
        print()
    else:
        print("기계 검사에서는 문제가 없습니다.\n")

    build_review(want, found, info)
    print(f"눈으로 확인할 검토표: {BASE / 'review.html'}")
    print("설명 문장과 화면이 맞는지, 개인정보가 가려졌는지는 사람이 봐야 합니다.")
    return 1 if problems else 0


REVIEW_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'IBM Plex Sans KR',system-ui,sans-serif;background:#F2F5F8;color:#14202C;
  font-size:15px;line-height:1.7;padding:36px 24px 90px}
.hd{max-width:1000px;margin:0 auto 28px;border-bottom:2px solid #14202C;padding-bottom:16px}
.hd h1{font-size:24px;letter-spacing:-.02em}
.hd p{color:#5D6E7D;font-size:13.5px;margin-top:6px}
.item{max-width:1000px;margin:0 auto 18px;background:#fff;border:1px solid #DCE3EA;
  border-radius:8px;padding:18px 20px;display:grid;grid-template-columns:1fr 300px;gap:22px}
.txt h3{font-size:12px;font-family:ui-monospace,monospace;color:#5D6E7D;letter-spacing:.08em;
  text-transform:uppercase;margin-bottom:7px}
.txt .act{font-size:16px;font-weight:600;margin-bottom:6px}
.txt .note{font-size:13.5px;color:#5D6E7D;border-left:2px solid #DCE3EA;padding-left:10px}
.txt .file{font-family:ui-monospace,monospace;font-size:11.5px;color:#93A3B1;margin-top:12px}
.ck{margin-top:14px;display:flex;gap:16px;font-size:13.5px}
.ck label{display:flex;gap:6px;align-items:center;cursor:pointer}
.pic{border:1px solid #DCE3EA;border-radius:6px;overflow:hidden;background:#F2F5F8}
.pic img{display:block;width:100%;height:auto}
.pic.none{display:grid;place-items:center;height:170px;color:#B23;font-size:13px}
a.zoom{display:block}
@media (max-width:820px){.item{grid-template-columns:1fr}}
"""


def build_review(want, found, info):
    rows = []
    for name in sorted(want):
        w = want[name]
        head = w["screen"] + (f" · {w['flow']}" if w["flow"] else "")
        if name in found:
            rel = os.path.relpath(found[name], BASE).replace("\\", "/")
            pic = (f'<a class="zoom" href="{rel}" target="_blank">'
                   f'<img src="{rel}" alt="{name}" loading="lazy"></a>')
        else:
            pic = '<div class="pic none">촬영되지 않음</div>'
        note = f'<div class="note">{w["note"]}</div>' if w["note"] else ""
        rows.append(f"""<div class="item">
<div class="txt">
  <h3>{head} · {w['no']}단계</h3>
  <div class="act">{w['action']}</div>
  {note}
  <div class="file">{name}</div>
  <div class="ck">
    <label><input type="checkbox"> 화면이 설명과 맞음</label>
    <label><input type="checkbox"> 개인정보 가려짐</label>
    <label><input type="checkbox"> 다시 찍어야 함</label>
  </div>
</div>
<div class="pic">{pic}</div>
</div>""")

    doc = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>캡처 검토표</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;600&display=swap" rel="stylesheet">
<style>{REVIEW_CSS}</style></head><body>
<div class="hd"><h1>캡처 검토표</h1>
<p>왼쪽 설명과 오른쪽 화면이 맞는지 확인하세요. 이미지를 클릭하면 원본 크기로 열립니다.
총 {len(want)}장 · 촬영됨 {len([n for n in want if n in found])}장</p></div>
{''.join(rows)}
</body></html>"""
    open(BASE / "review.html", "w", encoding="utf-8").write(doc)


if __name__ == "__main__":
    sys.exit(main())
