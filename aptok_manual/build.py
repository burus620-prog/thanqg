#!/usr/bin/env python3
"""아파트ok 매뉴얼 빌더 — 원본 YAML 하나에서 출력 3종을 생성한다.

  manual/src/*.yaml  →  ① site/index.html   웹 매뉴얼
                        ② out/faq.md        고객문의 응답용 FAQ 모음
                        ③ out/tooltips.json 인앱 툴팁 데이터
"""
import glob
import html
import json
import os
import re

import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "src")
CONFIG_NAMES = {"routes.yaml", "site.yaml"}   # 설정 파일은 원본으로 읽지 않는다
ACTION_WORDS = {"등록", "저장", "검색", "등록(저장)"}
# 캡처 폴더가 site/index.html 기준 어디에 있는지. 배치를 바꾸면 여기만 고친다.
IMG_BASE = "../captures"

# 제목은 site.yaml 이 있으면 거기서, 없으면 기본값
TITLE, SUBTITLE = "사용자 매뉴얼", ""
MENU_ORDER = []      # site.yaml 의 menu_order 로 목차 순서를 정한다
MENU_OPEN = []       # 처음부터 펼쳐 둘 대분류
SCREEN_ORDER = {}    # 대분류 안에서의 화면 순서 {대분류: [screen_id, ...]}
_cfg = os.path.join(BASE, "site.yaml")
if os.path.exists(_cfg):
    import yaml as _y
    _c = _y.safe_load(open(_cfg, encoding="utf-8")) or {}
    TITLE = _c.get("title", TITLE)
    SUBTITLE = _c.get("subtitle", SUBTITLE)
    MENU_ORDER = [str(x) for x in _c.get("menu_order", [])]
    MENU_OPEN = [str(x) for x in (_c.get("menu_open") or [])]
    SCREEN_ORDER = {str(k): [str(v) for v in (vs or [])]
                    for k, vs in (_c.get("screen_order") or {}).items()}


# ---------------------------------------------------------------- 로드

def source_files():
    """원본 yaml 을 찾는다. src 폴더와 최상위 폴더를 함께 본다.
    내려받은 파일이 어디에 놓이든 읽히도록 하기 위한 것이다."""
    found, seen = [], set()
    for folder in (SRC, BASE):
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".yaml") or name in CONFIG_NAMES:
                continue
            if name in seen:
                print(f"  ! {name} 이 두 곳에 있습니다. src 쪽을 씁니다.")
                continue
            seen.add(name)
            found.append(os.path.join(folder, name))
    return found


def _fix_keys(node):
    """YAML 1.1은 `no:`를 boolean False로 읽는다. 단계 번호 키를 되돌린다."""
    if isinstance(node, dict):
        if False in node:
            node["no"] = node.pop(False)
        for v in node.values():
            _fix_keys(v)
    elif isinstance(node, list):
        for v in node:
            _fix_keys(v)
    return node


def load():
    commons, screens = {}, []
    for path in source_files():
        for doc in yaml.safe_load_all(open(path, encoding="utf-8")):
            if not doc:
                continue
            for item in _fix_keys(doc):
                if item.get("doc_id"):
                    commons[item["doc_id"]] = item
                else:
                    screens.append(item)
    return commons, screens


# ---------------------------------------------------------------- 텍스트

def chips(text):
    """[등록] 같은 표기를 실제 버튼처럼 보이는 칩으로 바꾼다. 매뉴얼의 시각적 서명."""
    esc = html.escape(str(text)).strip()

    def repl(m):
        label = m.group(1)
        kind = "chip act" if label in ACTION_WORDS else "chip"
        return f'<b class="{kind}">{label}</b>'

    return re.sub(r"\[([^\]]{1,20})\]", repl, esc)


def block(text):
    return "".join(f"<p>{chips(p)}</p>" for p in str(text).strip().split("\n") if p.strip())


def anchor(sid):
    return re.sub(r"[^a-z0-9-]", "", str(sid).lower())


def plain_text(fragment):
    """완성된 HTML 조각에서 글자만 뽑는다. 검색 색인에 쓴다."""
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", fragment)
    t = re.sub(r"(?i)<(br|/p|/li|/h[1-6]|/td|/div)\s*/?>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------- 조각

def find_captures():
    """captures 폴더 아래 어디에 있든 png를 찾아 이름으로 색인한다.
    하위 폴더로 나뉘어 있든 한 폴더에 몰려 있든 상관없이 동작한다."""
    idx = {}
    root = os.path.join(BASE, "captures")
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".png"):
                idx.setdefault(f, os.path.join(dirpath, f))
    return idx


CAPTURES = {}       # build_site 에서 채운다
OUT_DIR = BASE      # 생성될 html 이 놓이는 폴더
EMBEDDED = []       # 실제로 붙은 이미지
MISSING = []        # 못 찾은 이미지


def steps_html(steps, title=None, screen_id=""):
    out = [f'<h4 class="sub">{html.escape(title)}</h4>'] if title else []
    out.append('<ol class="steps">')
    for s in steps:
        out.append('<li><div class="num">%s</div><div class="body">' % s.get("no", ""))
        out.append(f'<div class="act">{chips(s["action"])}</div>')
        if s.get("note"):
            out.append(f'<div class="note">{chips(s["note"])}</div>')
        if s.get("image"):
            name = s["image"]
            path = CAPTURES.get(name)
            if path:
                rel = os.path.relpath(path, OUT_DIR).replace("\\", "/")
                EMBEDDED.append(name)
                out.append(f'<figure class="shot has-img">'
                           f'<img src="{html.escape(rel)}" alt="{html.escape(name)}" loading="lazy">'
                           f'</figure>')
            else:
                MISSING.append(name)
                out.append(f'<div class="shot" data-src="{html.escape(name)}">'
                           f'<span>{html.escape(name)} · 아직 없음</span></div>')
        out.append("</div></li>")
    out.append("</ol>")
    return "".join(out)


def cautions_html(items):
    if not items:
        return ""
    lis = "".join(f"<li>{chips(c)}</li>" for c in items)
    return f'<div class="warn"><h4>주의</h4><ul>{lis}</ul></div>'


def faq_html(items):
    if not items:
        return ""
    rows = "".join(
        f'<details><summary>{chips(f["q"])}</summary><div>{block(f["a"])}</div></details>'
        for f in items
    )
    return f'<div class="faq"><h4 class="sub">자주 묻는 질문</h4>{rows}</div>'


def fields_html(fields):
    if not fields:
        return ""
    rows = ""
    for f in fields:
        req = '<span class="req">필수</span>' if f.get("required") else ""
        rows += (f'<tr><th>{html.escape(f["name"])}{req}</th>'
                 f'<td class="ty">{html.escape(str(f.get("type", "")))}</td>'
                 f'<td>{chips(f.get("desc", ""))}</td></tr>')
    return ('<h4 class="sub">입력 항목</h4><table class="fields">'
            f'<tbody>{rows}</tbody></table>')


# ---------------------------------------------------------------- 화면

def screen_html(sc, commons):
    a = anchor(sc["screen_id"])
    h = [f'<section id="{a}" class="screen">']
    h.append(f'<p class="path">{chips(sc.get("path", ""))}</p>')
    h.append(f'<h2>{html.escape(sc["screen_name"])}</h2>')

    meta = []
    if sc.get("pattern"):
        meta.append(f'<span class="tag">패턴 {html.escape(str(sc["pattern"]))}</span>')
    if sc.get("permission"):
        perm = sc["permission"]
        perm = " / ".join(perm) if isinstance(perm, list) else perm
        meta.append(f'<span class="tag perm">권한 · {html.escape(str(perm))}</span>')
    h.append(f'<div class="meta">{"".join(meta)}</div>')

    if sc.get("draft"):
        h.append('<div class="draft">이 화면은 아직 뼈대입니다. '
                 '화면 확인 후 내용을 채워야 합니다.</div>')

    if sc.get("purpose"):
        h.append(f'<div class="lede">{block(sc["purpose"])}</div>')

    if sc.get("why_first"):
        h.append(f'<div class="callout"><h4>먼저 읽어야 하는 이유</h4>{block(sc["why_first"])}</div>')

    h.append(extra_sections(sc))

    for pre in sc.get("prerequisite", []):
        h.append('<div class="callout pre"><h4>먼저 할 일</h4>'
                 f'<p><b>{chips(pre["screen"])}</b></p>{block(pre["desc"])}</div>')

    if sc.get("concepts"):
        rows = "".join(f'<tr><th>{html.escape(c["term"])}</th><td>{chips(c["desc"])}</td></tr>'
                       for c in sc["concepts"])
        h.append(f'<h4 class="sub">용어</h4><table class="fields"><tbody>{rows}</tbody></table>')

    inh = sc.get("inherits")
    if inh and inh in commons:
        cname = commons[inh].get("doc_name", inh)
        h.append(f'<p class="xref">기본 조작은 '
                 f'<a href="#{anchor(inh)}">{html.escape(cname)}</a>에 정리되어 있습니다. '
                 f'아래에는 이 화면에만 해당하는 내용만 적었습니다.</p>')

    if sc.get("columns"):
        cols = "".join(f'<li>{html.escape(c)}</li>' for c in sc["columns"])
        h.append(f'<h4 class="sub">표에 보이는 항목</h4><ul class="cols">{cols}</ul>')

    if sc.get("screen_specific"):
        rows = "".join(f'<tr><th>{chips(s["name"])}</th><td>{chips(s["desc"])}</td></tr>'
                       for s in sc["screen_specific"])
        h.append(f'<h4 class="sub">이 화면에만 있는 기능</h4>'
                 f'<table class="fields"><tbody>{rows}</tbody></table>')

    h.append(fields_html(sc.get("fields")))

    if sc.get("steps"):
        h.append(steps_html(sc["steps"], "따라 하기", sc["screen_id"]))

    for sf in (sc.get("sub_flows") or []):
        h.append(steps_html(sf["steps"], sf["name"], sc["screen_id"]))

    h.append(cautions_html(sc.get("cautions")))
    h.append(faq_html((sc.get("faq") or [])))

    if sc.get("privacy_note"):
        h.append(f'<div class="warn priv"><h4>개인정보</h4>{block(sc["privacy_note"])}</div>')

    h.append("</section>")
    return "".join(h)


# 공통 문서의 추가 항목을 화면에 그린다. 여기 없는 이름은 그대로 제목으로 쓴다.
SECTION_LABELS = {
    "key_concept": "핵심", "relation": "다른 메뉴와의 관계",
    "before_you_start": "시작하기 전에", "why_it_matters": "왜 해야 하나",
    "when_to_use": "언제 쓰나", "what_each_shows": "각 서식이 보여주는 것",
    "what_each_is": "각 신고가 무엇인가", "what_goes_where": "무엇을 어디에 넣나",
    "cycle": "주기", "order": "순서", "money_flow": "돈의 흐름",
    "where_numbers_come_from": "숫자가 이상할 때", "how_to_submit": "제출 방법",
    "deadline": "기한", "deadline_example": "예시", "why_first": "먼저 읽어야 하는 이유",
}
SKIP_KEYS = {"doc_id", "doc_name", "applies_to_pattern", "applies_count", "purpose",
             "layout", "common_actions", "common_cautions", "common_faq",
             "screen_id", "screen_name", "path", "pattern", "inherits", "permission",
             "draft", "steps", "sub_flows", "cautions", "faq", "columns", "fields",
             "concepts", "screen_specific", "observed_state", "privacy_note",
             "prerequisite", "legal_basis", "sources"}


def extra_sections(item):
    """정해진 틀 밖의 항목도 빠짐없이 그린다."""
    out = []
    for key, val in item.items():
        if key in SKIP_KEYS or not val:
            continue
        label = SECTION_LABELS.get(key, key.replace("_", " "))
        if isinstance(val, str):
            out.append(f'<div class="callout"><h4>{html.escape(label)}</h4>'
                       f'{block(val)}</div>')
        elif isinstance(val, list):
            rows = ""
            for v in val:
                if isinstance(v, dict):
                    ks = list(v.keys())
                    head = str(v.get(ks[0], ""))
                    body_ = " ".join(str(v[k]) for k in ks[1:])
                    rows += (f'<tr><th>{chips(head)}</th>'
                             f'<td>{chips(body_)}</td></tr>')
                else:
                    rows += f'<tr><td colspan="2">{chips(v)}</td></tr>'
            out.append(f'<h4 class="sub">{html.escape(label)}</h4>'
                       f'<table class="fields"><tbody>{rows}</tbody></table>')
    return "".join(out)


def common_html(c):
    h = [f'<section id="{anchor(c["doc_id"])}" class="screen">']
    h.append('<p class="path">공통 문서</p>')
    h.append(f'<h2>{html.escape(c["doc_name"])}</h2>')
    n = c.get("applies_count")
    h.append('<div class="meta"><span class="tag">'
             + (f"{n}개 화면 공통" if n else "공통 문서") + '</span></div>')
    h.append(f'<div class="lede">{block(c["purpose"])}</div>')
    h.append(extra_sections(c))

    if c.get("layout"):
        rows = "".join(f'<tr><th>{html.escape(z["zone"])}</th><td>{chips(z["desc"])}</td></tr>'
                       for z in c["layout"])
        h.append(f'<h4 class="sub">화면 구성</h4><table class="fields"><tbody>{rows}</tbody></table>')

    for act in c.get("common_actions", []):
        h.append(f'<div class="action"><h4>{chips(act["name"])}</h4><ol class="plain">')
        h.extend(f"<li>{chips(s)}</li>" for s in act["steps"])
        h.append("</ol>")
        if act.get("note"):
            h.append(f'<p class="note">{chips(act["note"])}</p>')
        if act.get("caution"):
            h.append(f'<div class="warn tight"><ul><li>{chips(act["caution"])}</li></ul></div>')
        h.append("</div>")

    h.append(cautions_html(c.get("common_cautions")))
    h.append(faq_html(c.get("common_faq")))
    h.append("</section>")
    return "".join(h)


# ---------------------------------------------------------------- 출력 ①

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --ink:#14202C; --muted:#5D6E7D; --line:#DCE3EA;
  --paper:#fff; --surface:#F2F5F8;
  --accent:#E8455F; --action:#0E9E92;
  --warn:#9A5B08; --warn-bg:#FDF4E3;
  --sans:'IBM Plex Sans KR',system-ui,sans-serif;
  --disp:'Hahmlet',serif; --mono:'IBM Plex Mono',monospace;
}
body{font-family:var(--sans);color:var(--ink);background:var(--surface);
  font-size:15px;line-height:1.75;-webkit-font-smoothing:antialiased}
.wrap{display:grid;grid-template-columns:264px minmax(0,1fr);gap:0;
  max-width:1180px;margin:0 auto;background:var(--paper);min-height:100vh}

/* 좌측 목차 — 제품의 왼쪽 메뉴와 같은 자리 */
.nav{border-right:1px solid var(--line);padding:34px 22px 60px;
  position:sticky;top:0;height:100vh;overflow-y:auto;background:var(--paper)}
.brand{font-family:var(--disp);font-size:21px;font-weight:700;letter-spacing:-.02em;
  line-height:1.3;margin-bottom:4px}
.brand em{font-style:normal;color:var(--accent)}
.brand-sub{font-size:12px;color:var(--muted);margin-bottom:26px;letter-spacing:.02em}
.nav h5{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;color:var(--muted);
  text-transform:uppercase;margin:22px 0 8px}
.nav a{display:block;padding:6px 10px;margin-left:-10px;border-radius:5px;
  color:var(--ink);text-decoration:none;font-size:13.5px}
.nav a:hover{background:var(--surface)}
.nav a.on{color:var(--accent);font-weight:600}

/* 검색 */
.search{position:relative;margin:0 0 6px}
.search input{width:100%;padding:9px 30px 9px 11px;border:1px solid var(--line);
  border-radius:6px;background:#fff;font:inherit;font-size:13.5px;color:var(--ink)}
.search input::placeholder{color:var(--muted)}
.search input:focus{outline:none;border-color:var(--ink)}
.search input::-webkit-search-cancel-button{display:none}
.search button{position:absolute;right:6px;top:50%;transform:translateY(-50%);
  border:0;background:none;cursor:pointer;font-size:17px;line-height:1;
  color:var(--muted);padding:2px 5px}
.search button:hover{color:var(--ink)}
.results{margin-bottom:8px}
.results .cnt{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;
  color:var(--muted);padding:8px 0 6px}
.results a{display:block;padding:9px 10px;margin-left:-10px;border-radius:6px;
  color:var(--ink);text-decoration:none;border-bottom:1px solid var(--line)}
.results a:hover,.results a.sel{background:var(--surface)}
.results .rn{font-size:13.5px;font-weight:600;display:block}
.results .rp{font-size:11px;color:var(--muted);display:block;margin-top:2px}
.results .rt{font-size:12px;color:#5A6875;display:block;margin-top:5px;line-height:1.55}
.results mark{background:#FFF0B3;color:inherit;border-radius:2px;padding:0 1px}
.results .none{font-size:13px;color:var(--muted);padding:14px 0;line-height:1.7}

/* 대분류 — 눌러서 접고 편다 */
.grp{border-bottom:1px solid var(--line)}
.grp>summary{list-style:none;cursor:pointer;padding:11px 22px 11px 0;position:relative;
  font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;color:var(--muted);
  text-transform:uppercase;user-select:none}
.grp>summary::-webkit-details-marker{display:none}
.grp>summary:hover{color:var(--ink)}
.grp[open]>summary{color:var(--ink);font-weight:500}
.grp>summary::after{content:"+";position:absolute;right:2px;top:9px;
  font-family:var(--mono);font-size:13px;color:var(--muted)}
.grp[open]>summary::after{content:"−"}
.grp-in{padding-bottom:10px}
.nav .nav-sub{font-size:11.5px;color:var(--muted);margin:9px 0 3px;letter-spacing:.02em}
.nav a.ind{padding-left:20px;margin-left:-10px}
.nav a.ind::before{content:"·";color:var(--muted);margin-right:7px}

.main{padding:52px 56px 120px;max-width:820px}
.masthead{border-bottom:2px solid var(--ink);padding-bottom:22px;margin-bottom:14px}
.masthead h1{font-family:var(--disp);font-size:34px;font-weight:700;letter-spacing:-.03em;line-height:1.25}
.masthead p{color:var(--muted);font-size:13.5px;margin-top:8px}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12.5px;color:var(--muted);
  padding:14px 0 0;margin-bottom:46px}

.screen{padding:44px 0;border-top:1px solid var(--line)}
.screen:first-of-type{border-top:0}
.path{font-family:var(--mono);font-size:11.5px;color:var(--muted);letter-spacing:.02em;margin-bottom:6px}
.screen h2{font-family:var(--disp);font-size:26px;font-weight:700;letter-spacing:-.02em;line-height:1.35}
.meta{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0 20px}
.tag{font-family:var(--mono);font-size:11px;padding:3px 9px;border:1px solid var(--line);
  border-radius:20px;color:var(--muted)}
.tag.perm{border-color:#F6C9D1;color:var(--accent)}
.lede{font-size:16px;line-height:1.8}
.lede p+p{margin-top:8px}
h4.sub{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);margin:38px 0 14px;padding-bottom:7px;border-bottom:1px solid var(--line)}

/* 서명 요소 — 화면 속 버튼을 그대로 옮긴 칩 */
.chip{font-family:var(--sans);font-weight:600;font-size:12.5px;font-style:normal;
  padding:2px 8px;border:1px solid var(--line);border-radius:4px;background:#fff;
  box-shadow:0 1px 0 rgba(20,32,44,.06);white-space:nowrap}
.chip.act{background:var(--action);border-color:var(--action);color:#fff;box-shadow:none}

.steps{list-style:none;counter-reset:s}
.steps li{display:grid;grid-template-columns:34px 1fr;gap:16px;padding-bottom:22px;position:relative}
.steps li:not(:last-child)::before{content:"";position:absolute;left:16.5px;top:32px;bottom:0;
  width:1px;background:var(--line)}
.num{font-family:var(--mono);font-size:12px;width:34px;height:34px;display:grid;place-items:center;
  border:1px solid var(--ink);border-radius:3px;background:var(--paper);position:relative;z-index:1}
.act{font-size:15.5px;padding-top:5px}
.note{font-size:13.5px;color:var(--muted);margin-top:6px;padding-left:11px;
  border-left:2px solid var(--line)}
.shot{margin-top:10px;height:74px;border:1px dashed var(--line);border-radius:5px;
  background:var(--surface);display:grid;place-items:center}
.shot span{font-family:var(--mono);font-size:11px;color:#93A3B1}
figure.shot{height:auto;border:1px solid var(--line);border-radius:6px;overflow:hidden;
  background:var(--paper);padding:0;display:block}
figure.shot img{display:block;width:100%;height:auto}

.plain{padding-left:19px;font-size:14.5px}
.plain li{margin-bottom:3px}
.action{padding:18px 0;border-bottom:1px solid var(--line)}
.action h4{font-size:15.5px;font-weight:600;margin-bottom:9px}

table.fields{width:100%;border-collapse:collapse;font-size:14px}
table.fields th{text-align:left;vertical-align:top;padding:11px 14px 11px 0;width:132px;
  font-weight:600;border-bottom:1px solid var(--line)}
table.fields td{vertical-align:top;padding:11px 0;border-bottom:1px solid var(--line);color:#33424F}
td.ty{width:84px;font-family:var(--mono);font-size:11.5px;color:var(--muted);padding-right:14px}
.req{display:inline-block;font-family:var(--mono);font-size:9.5px;color:var(--accent);
  border:1px solid #F6C9D1;border-radius:3px;padding:0 4px;margin-left:6px;vertical-align:2px}
ul.cols{list-style:none;display:flex;flex-wrap:wrap;gap:6px}
ul.cols li{font-family:var(--mono);font-size:12px;padding:3px 9px;background:var(--surface);
  border-radius:4px;color:#455563}

.callout{background:var(--surface);border-left:3px solid var(--ink);padding:16px 18px;
  margin:24px 0;border-radius:0 5px 5px 0}
.callout.pre{border-left-color:var(--accent)}
.callout h4{font-size:12.5px;letter-spacing:.02em;margin-bottom:6px}
.callout p{font-size:14.5px}
.draft{background:#FFF4E6;border:1px dashed #E8A33D;color:#8A5A0B;
  font-size:13.5px;padding:10px 14px;border-radius:5px;margin:16px 0}
.xref{font-size:14px;background:var(--surface);padding:13px 16px;border-radius:5px;margin:22px 0}
.xref a{color:var(--accent);font-weight:600}

.warn{background:var(--warn-bg);border-radius:5px;padding:16px 18px;margin:26px 0}
.warn.tight{margin:10px 0;padding:11px 16px}
.warn h4{font-size:12.5px;color:var(--warn);margin-bottom:7px}
.warn ul{padding-left:17px;font-size:14.5px;color:#5B4210}
.warn li+li{margin-top:5px}
.warn.priv{background:#FDF0F2}
.warn.priv h4{color:var(--accent)}
.warn.priv p{font-size:14.5px;color:#6E2733}

.faq details{border-bottom:1px solid var(--line)}
.faq summary{cursor:pointer;padding:13px 0;font-size:14.5px;font-weight:600;list-style:none;
  display:flex;justify-content:space-between;gap:14px}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";font-family:var(--mono);color:var(--muted)}
.faq details[open] summary::after{content:"−"}
.faq details>div{padding:0 0 15px;font-size:14.5px;color:#33424F}

a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
@media (max-width:860px){
  .wrap{grid-template-columns:1fr}
  .nav{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line);padding:26px 22px}
  .main{padding:34px 22px 80px}
  .masthead h1{font-size:27px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

JS = """
const links=[...document.querySelectorAll('.nav a')];

/* 지금 보고 있는 화면을 목차에서 표시하고, 그 화면이 든 대분류는 펼쳐 준다. */
function mark(a){
  links.forEach(l=>l.classList.toggle('on',l===a));
  if(!a) return;
  const g=a.closest('details.grp');
  if(g&&!g.open) g.open=true;
}
/* 오래된 브라우저에는 IntersectionObserver 가 없다.
   없다고 여기서 멈추면 아래 검색까지 죽으므로 있을 때만 쓴다. */
if(window.IntersectionObserver){
  const obs=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){
    mark(links.find(l=>l.getAttribute('href')==='#'+e.target.id));}});},
    {rootMargin:'-15% 0px -75% 0px'});
  document.querySelectorAll('.screen').forEach(s=>obs.observe(s));
}

/* 접힌 대분류 안의 화면으로 바로 들어와도 그 묶음을 펼친다. */
function openTarget(){
  const id=location.hash.slice(1);
  if(!id) return;
  const a=links.find(l=>l.getAttribute('href')==='#'+id);
  if(a){const g=a.closest('details.grp'); if(g) g.open=true;}
}
addEventListener('hashchange',openTarget);
openTarget();

/* 접고 편 상태를 기억한다. 다시 열었을 때 보던 대로 나온다. */
const KEY='aptok-nav-open';
let saved=null;
try{saved=JSON.parse(localStorage.getItem(KEY));}catch(e){}
document.querySelectorAll('details.grp[data-top]').forEach(g=>{
  const t=g.dataset.top;
  if(saved&&t in saved) g.open=saved[t];
  g.addEventListener('toggle',()=>{
    let s={};
    try{s=JSON.parse(localStorage.getItem(KEY))||{};}catch(e){}
    s[t]=g.open;
    try{localStorage.setItem(KEY,JSON.stringify(s));}catch(e){}
  });
});
openTarget();

/* ---------------------------------------------------------------- 검색
   화면마다 본문 전체가 색인에 들어 있다. 제목이든 주의사항이든 문답이든
   글자만 맞으면 걸린다. 낱말을 띄어 적으면 모두 든 화면만 남는다. */
const IDX=JSON.parse(document.getElementById('idx').textContent);
const qi=document.getElementById('q'), qx=document.getElementById('qx'),
      qr=document.getElementById('qr'), tree=document.getElementById('tree');
const esc=s=>s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const rx=s=>s.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&');

/* 찾은 낱말 앞뒤를 잘라 보여준다. */
function snip(text,words){
  const first=text.toLowerCase().indexOf(words[0].toLowerCase());
  if(first<0) return '';
  const a=Math.max(0,first-45), b=Math.min(text.length,first+135);
  let s=esc(text.slice(a,b));
  words.forEach(w=>{s=s.replace(new RegExp(rx(esc(w)),'gi'),m=>'<mark>'+m+'</mark>');});
  return (a>0?'…':'')+s+(b<text.length?'…':'');
}

function run(){
  const raw=qi.value.trim();
  qx.hidden=!raw;
  if(!raw){qr.hidden=true;qr.innerHTML='';tree.hidden=false;return;}
  const words=raw.split(/\\s+/).filter(Boolean);
  const hits=[];
  for(const d of IDX){
    const hay=(d.n+' '+d.p+' '+d.t).toLowerCase();
    if(!words.every(w=>hay.includes(w.toLowerCase()))) continue;
    /* 화면 이름에 든 것을 위로 올린다. */
    const inName=words.some(w=>d.n.toLowerCase().includes(w.toLowerCase()));
    hits.push({d:d,rank:inName?0:1});
  }
  hits.sort((x,y)=>x.rank-y.rank);
  tree.hidden=true; qr.hidden=false;
  if(!hits.length){
    qr.innerHTML='<div class="none"><b>'+esc(raw)+'</b> 에 맞는 화면이 없습니다.<br>'
      +'낱말 수를 줄이거나 다른 말로 찾아보세요.</div>';
    return;
  }
  qr.innerHTML='<div class="cnt">'+hits.length+'개 화면</div>'
    +hits.map(h=>'<a href="#'+h.d.i+'"><span class="rn">'+esc(h.d.n)+'</span>'
      +'<span class="rp">'+esc(h.d.p)+'</span>'
      +(h.rank?'<span class="rt">'+snip(h.d.t,words)+'</span>':'')+'</a>').join('');
}

/* 결과를 누르면 목차로 돌아가고, 그 화면이 든 대분류를 펼친다. */
qr.addEventListener('click',e=>{
  const a=e.target.closest('a'); if(!a) return;
  qi.value=''; run(); setTimeout(openTarget,0);
});
qi.addEventListener('input',run);
qx.addEventListener('click',()=>{qi.value='';run();qi.focus();});

/* 위아래 화살표로 고르고 엔터로 연다. Esc 로 지운다. */
qi.addEventListener('keydown',e=>{
  if(e.key==='Escape'){qi.value='';run();return;}
  const rs=[...qr.querySelectorAll('a')]; if(!rs.length) return;
  let i=rs.findIndex(r=>r.classList.contains('sel'));
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){
    e.preventDefault();
    if(i>=0) rs[i].classList.remove('sel');
    i=e.key==='ArrowDown'?(i+1)%rs.length:(i<=0?rs.length-1:i-1);
    rs[i].classList.add('sel');
    if(rs[i].scrollIntoView) rs[i].scrollIntoView({block:'nearest'});
  }else if(e.key==='Enter'){
    e.preventDefault(); (i>=0?rs[i]:rs[0]).click();
  }
});

/* Ctrl+K (맥은 ⌘K) 또는 / 로 검색칸에 바로 들어간다. */
addEventListener('keydown',e=>{
  const typing=/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  if(((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k')||(e.key==='/'&&!typing)){
    e.preventDefault(); qi.focus(); qi.select();
  }
});
"""


def build_site(commons, screens, out):
    global CAPTURES, OUT_DIR
    CAPTURES = find_captures()
    OUT_DIR = os.path.dirname(os.path.abspath(out))
    # 목차는 site.yaml 의 menu_order 를 따른다. 없으면 나온 순서대로 둔다.
    groups = {}
    for sc in screens:
        top = str(sc.get("path", "기타")).split(">")[0].strip()
        groups.setdefault(top, []).append(sc)
    groups = dict(sorted(groups.items(),
                         key=lambda kv: (MENU_ORDER.index(kv[0])
                                         if kv[0] in MENU_ORDER else 99, kv[0])))

    # 대분류 안의 화면 순서. site.yaml 의 screen_order 에 적힌 것이 앞에 오고,
    # 적히지 않은 화면은 원본에 나온 순서 그대로 뒤에 붙는다.
    for top, items in groups.items():
        want = SCREEN_ORDER.get(top)
        if want:
            items.sort(key=lambda sc: (want.index(sc["screen_id"])
                                       if sc["screen_id"] in want else len(want)))

    def sub_group(sc):
        """path 의 가운데 마디. '민원관리 > 통화매니저 > 설정' 이면 '통화매니저'.
        마디가 둘뿐이면 하위 묶음이 없다는 뜻이라 None."""
        parts = [p.strip() for p in str(sc.get("path", "")).split(">")]
        if len(parts) >= 3 and not parts[1].startswith("["):
            return parts[1]
        return None

    nav = [f'<div class="brand">{html.escape(TITLE)}</div>'
           f'<div class="brand-sub">{html.escape(SUBTITLE)}</div>',
           '<div class="search">'
           '<input id="q" type="search" autocomplete="off" placeholder="검색 (Ctrl+K)" '
           'aria-label="매뉴얼 검색">'
           '<button id="qx" type="button" aria-label="지우기" hidden>×</button>'
           '</div>'
           '<div id="qr" class="results" hidden></div>'
           '<div id="tree">']
    if commons:
        nav.append('<details class="grp" open><summary>공통</summary><div class="grp-in">')
        for cid, c in commons.items():
            nav.append(f'<a href="#{anchor(cid)}">{html.escape(c["doc_name"])}</a>')
        nav.append("</div></details>")
    for top, items in groups.items():
        op = " open" if top in MENU_OPEN else ""
        nav.append(f'<details class="grp" data-top="{html.escape(top)}"{op}>'
                   f"<summary>{html.escape(top)}</summary><div class=\"grp-in\">")
        # 묶음 이름과 같은 이름의 화면이 이미 목차에 있으면 머리글을 따로 달지 않는다.
        # ('설문 관리' 아래에 다시 [설문 관리] 라고 쓰지 않기 위한 것)
        own = [sc["screen_name"] for sc in items if not sub_group(sc)]
        dup = {s for s in (sub_group(sc) for sc in items)
               if s and any(n.startswith(s) for n in own)}
        seen_sub = None
        for sc in items:
            sub = sub_group(sc)
            if sub != seen_sub:
                if sub and sub not in dup:
                    nav.append(f'<div class="nav-sub">{html.escape(sub)}</div>')
                seen_sub = sub
            cls = ' class="ind"' if sub else ""
            nav.append(f'<a href="#{anchor(sc["screen_id"])}"{cls}>'
                       f'{html.escape(sc["screen_name"])}</a>')
        nav.append("</div></details>")

    nav.append("</div>")   # #tree 닫기

    # 본문도 목차와 같은 순서로 낸다.
    screens = [sc for items in groups.values() for sc in items]
    body = [common_html(c) for c in commons.values()]
    body += [screen_html(sc, commons) for sc in screens]

    # 검색 색인 — 화면마다 실제로 그려진 글자를 그대로 담는다.
    # 원본 YAML 이 아니라 완성된 HTML 에서 뽑으므로, 화면에 보이는 것과 어긋나지 않는다.
    index = []
    for h, item in ([(body[i], c) for i, c in enumerate(commons.values())]
                    + [(body[len(commons) + i], sc) for i, sc in enumerate(screens)]):
        sid = item.get("screen_id") or item.get("doc_id")
        name = item.get("screen_name") or item.get("doc_name")
        index.append({
            "i": anchor(sid),
            "n": name,
            "p": str(item.get("path") or "공통"),
            "t": plain_text(h)[:2500],
        })
    index_json = json.dumps(index, ensure_ascii=False, separators=(",", ":"))

    doc = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>아파트ok 사용자 매뉴얼</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Hahmlet:wght@500;700&family=IBM+Plex+Sans+KR:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<div class="wrap">
<nav class="nav">{"".join(nav)}</nav>
<main class="main">
<header class="masthead">
<h1>{html.escape(TITLE)}</h1>
<p>{html.escape(SUBTITLE)} · {len(screens)}개 화면</p>
</header>
<div class="legend">
<span><b class="chip">목록</b> 화면에 있는 버튼</span>
<span><b class="chip act">등록</b> 저장·실행 버튼</span>
<span>점선 칸은 화면 캡처가 들어갈 자리</span>
</div>
{"".join(body)}
</main></div>
<script id="idx" type="application/json">{index_json}</script>
<script>{JS}</script></body></html>"""

    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(doc)
    return out


# ---------------------------------------------------------------- 출력 ②③

def build_faq(commons, screens, out):
    lines = ["# 아파트ok 자주 묻는 질문", "",
             "원본 YAML에서 자동 생성됨. 고객문의 응답·챗봇 학습용.", ""]
    n = 0
    for c in commons.values():
        if c.get("common_faq"):
            lines += [f"## {c['doc_name']}", ""]
            for f in c["common_faq"]:
                lines += [f"**Q. {f['q']}**", "", f"A. {str(f['a']).strip()}", ""]
                n += 1
    for sc in screens:
        if not (sc.get("faq") or []):
            continue
        lines += [f"## {sc['screen_name']}", "", f"`{sc.get('path','')}`", ""]
        for f in sc["faq"]:
            lines += [f"**Q. {f['q']}**", "", f"A. {str(f['a']).strip()}", ""]
            n += 1
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    return out, n


def build_tooltips(screens, out):
    data, n = {}, 0
    for sc in screens:
        tips = []
        for s in (sc.get("steps") or []):
            if s.get("target"):
                tips.append({"step": s.get("no"), "target": s["target"],
                             "text": re.sub(r"[\[\]]", "", str(s["action"])).strip()})
        for c in (sc.get("cautions") or []):
            tips.append({"type": "caution", "text": re.sub(r"[\[\]]", "", str(c)).strip()})
        if tips:
            data[sc["screen_id"]] = {"screen": sc["screen_name"],
                                     "path": sc.get("path", ""), "tips": tips}
            n += len(tips)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out, n


if __name__ == "__main__":
    commons, screens = load()
    print(f"원본 폴더 : {SRC} (최상위 폴더의 yaml 도 함께 읽습니다)")
    print(f"캡처 폴더 : {os.path.join(BASE, 'captures')}")
    site = build_site(commons, screens, os.path.join(BASE, "site/index.html"))
    faq, nf = build_faq(commons, screens, os.path.join(BASE, "out/faq.md"))
    tip, nt = build_tooltips(screens, os.path.join(BASE, "out/tooltips.json"))
    print(f"\n원본 {len(screens)}개 화면 + 공통문서 {len(commons)}개")
    print(f"캡처 이미지 {len(CAPTURES)}장 발견 · 매뉴얼에 붙임 {len(EMBEDDED)}장 · 자리 비움 {len(MISSING)}장")
    if MISSING:
        print("  못 찾은 이미지: " + ", ".join(sorted(set(MISSING))[:6])
              + (" ..." if len(set(MISSING)) > 6 else ""))
    print(f"  ① {site}  ({os.path.getsize(site):,} bytes)")
    print(f"  ② {faq}  (문답 {nf}개)")
    print(f"  ③ {tip}  (툴팁 {nt}개)")
