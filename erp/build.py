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
IMG_BASE = "captures"

# 제목은 site.yaml 이 있으면 거기서, 없으면 기본값
TITLE, SUBTITLE = "사용자 매뉴얼", ""
MENU_ORDER = []      # site.yaml 의 menu_order 로 목차 순서를 정한다
_cfg = os.path.join(BASE, "site.yaml")
if os.path.exists(_cfg):
    import yaml as _y
    _c = _y.safe_load(open(_cfg, encoding="utf-8")) or {}
    TITLE = _c.get("title", TITLE)
    SUBTITLE = _c.get("subtitle", SUBTITLE)
    MENU_ORDER = [str(x) for x in _c.get("menu_order", [])]


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

    return bold(re.sub(r"\[([^\]]{1,20})\]", repl, esc))


def bold(fragment):
    """**굵게** 표기를 <strong> 으로 바꾼다. chips() 뒤에 적용한다."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", fragment, flags=re.S)


def block(text):
    return "".join(f"<p>{chips(p)}</p>" for p in str(text).strip().split("\n") if p.strip())


def anchor(sid):
    return re.sub(r"[^a-z0-9-]", "", str(sid).lower())


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
                if rel.startswith("../captures/"): rel = rel[3:]
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
        h.append('<div class="draft">이 화면은 메뉴 위치와 기본 조작만 안내합니다. '
                 '자세한 설명은 준비 중입니다.</div>')

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
    "inventory_note": "물건을 다루는 업종이라면",
    "business_types": "사업자 유형",
    "set_your_type": "내 유형 설정하기",
    "when_to_file": "신고 시기",
    "what_counts_as_deduction": "공제받을 수 있는 매입",
    "not_deductible": "공제되지 않는 매입",
    "five_steps": "신고 다섯 단계",
    "before_you_file": "신고 전에 확인할 것",
    "common_mistakes": "자주 하는 실수",
    "income_types": "소득 종류",
    "which_type": "어느 소득으로 볼 것인가",
    "how_to_judge": "판단 기준",
    "half_year_special": "반기납부 특례",
    "deemed_payment": "지급시기 의제",
    "small_biz_credit": "소규모 사업자 세액공제",
    "yearend_link": "연말정산과의 관계",
    "three_filings": "제출 서류 세 가지",
    "submit_cycle": "소득별 제출 주기",
    "not_supported": "이 서비스에서 만들 수 없는 서류",
    "file_at_hometax": "홈택스에서 직접 신고할 서류",
    "which_menu": "상황별 이용 메뉴",
    "submit_method": "제출 방법",
    "after_payment": "신고·납부 후 할 일",
    "penalty": "가산세",
    "relation_to_others": "다른 신고와의 관계",
    "buttons": "화면의 버튼",
    "flow": "진행 흐름",
    "where_is_my_doc": "내 문서 찾기",
    "screens_at_a_glance": "화면 한눈에 보기",
    "who_needs_this": "어떤 사업장이 쓰나",
    "where_is_the_menu": "메뉴 위치",
    "how_it_connects": "다른 기능과의 연결",
    "setup_first": "먼저 등록할 것",
    "setup_order": "설정 순서",
    "what_breaks_without_it": "빠뜨리면 생기는 일",
    "three_worker_types": "직원 구분 세 가지",
    "payslip_duty": "임금명세서 교부 의무",
    "seven_groups": "보고서 갈래",
    "three_roles": "결재 역할 세 가지",
    "what_you_enter": "입력 항목",
    "required_fields": "필수 항목",
    "other_sections": "그 밖의 항목",
    "what_you_register": "등록할 수 있는 것",
    "auth_methods": "인증 수단",
    "how_to_fill": "채우는 방법",
    "user_types": "사용자 유형",
    "multi_business": "사업장이 여러 개일 때",
    "structure": "거래명 구조",
    "cautions_extra": "추가 주의사항",
    "after_this": "이후에 할 일",
    "unissued_unreceived": "미발행 · 미수취",
    "where_in_flow": "신고 흐름에서의 위치",
    "three_steps": "진행 세 단계",
    "attached_forms": "부속서류",
    "income_codes": "소득 코드",
    "late_filing": "기한후신고",
    "can_submit_directly": "바로 제출할 수 있나",
    "form_structure": "서식 구성",
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
.draft{background:#F4F5F6;border:1px solid #DFE3E6;color:#5B6770;
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

/* Sidebar Search */
.nav-search {
  position: relative;
  margin-bottom: 18px;
}
.nav-search input {
  width: 100%;
  padding: 8px 30px 8px 32px;
  font-family: var(--sans);
  font-size: 13px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
  color: var(--ink);
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s, background-color 0.2s;
}
.nav-search input:focus {
  background: var(--paper);
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(232, 69, 95, 0.12);
}
.nav-search .search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 14px;
  color: var(--muted);
  pointer-events: none;
}
.nav-search .search-clear {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  border: none;
  background: var(--line);
  color: var(--muted);
  border-radius: 50%;
  font-size: 12px;
  cursor: pointer;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
}
.nav-search .search-clear:hover {
  background: var(--muted);
  color: #fff;
}
.nav-search input:not(:placeholder-shown) + .search-clear {
  display: flex;
}

/* Category Headers & Collapsible Groups */
.nav-group {
  margin-bottom: 6px;
  border-bottom: 1px solid rgba(220, 227, 234, 0.5);
  padding-bottom: 6px;
}
.nav-group:last-child {
  border-bottom: none;
}
.nav-cat {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 10px;
  margin-left: -10px;
  border: none;
  background: transparent;
  color: var(--ink);
  font-family: var(--sans);
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: -0.01em;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.15s ease, color 0.15s ease;
  user-select: none;
  text-align: left;
}
.nav-cat:hover {
  background: var(--surface);
  color: var(--accent);
}
.nav-cat-info {
  display: flex;
  align-items: center;
  gap: 6px;
}
.nav-cat-badge {
  font-size: 10.5px;
  font-family: var(--mono);
  font-weight: 500;
  color: var(--muted);
  background: var(--surface);
  padding: 1px 6px;
  border-radius: 10px;
  border: 1px solid var(--line);
}
.nav-cat .arrow-icon {
  width: 12px;
  height: 12px;
  color: var(--muted);
  transition: transform 0.2s ease;
  flex-shrink: 0;
}
.nav-group.open .arrow-icon {
  transform: rotate(180deg);
  color: var(--accent);
}
.nav-group:not(.open) .nav-sub {
  display: none;
}
.nav-sub {
  padding-left: 4px;
  margin-top: 2px;
  margin-bottom: 6px;
}
.nav-sub a {
  display: block;
  padding: 5px 10px 5px 12px;
  margin-left: -10px;
  border-radius: 5px;
  color: var(--ink);
  text-decoration: none;
  font-size: 13px;
  line-height: 1.5;
  transition: background 0.15s, color 0.15s;
}
.nav-sub a:hover {
  background: var(--surface);
  color: var(--accent);
}
.nav-sub a.on {
  color: var(--accent);
  font-weight: 600;
  background: rgba(232, 69, 95, 0.08);
}

/* Search empty & highlight */
.search-empty {
  padding: 20px 10px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
  display: none;
}
.search-highlight {
  background: #FFE8EC;
  color: var(--accent);
  font-weight: 600;
  border-radius: 2px;
  padding: 0 1px;
}

@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

JS = """
(function() {
  function initManualNav() {
    const groups = document.querySelectorAll('.nav-group');
    const searchInput = document.getElementById('menu-search-input');
    const searchClear = document.getElementById('search-clear-btn');
    const searchEmpty = document.getElementById('search-empty');
    const links = Array.from(document.querySelectorAll('.nav-sub a'));

    groups.forEach(group => {
      const btn = group.querySelector('.nav-cat');
      if (btn) {
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          const isOpen = group.classList.toggle('open');
          btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        });
      }
    });

    if ('IntersectionObserver' in window) {
      const obs = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const targetId = '#' + entry.target.id;
            links.forEach(link => {
              const isMatch = link.getAttribute('href') === targetId;
              link.classList.toggle('on', isMatch);
              if (isMatch && searchInput && !searchInput.value.trim()) {
                const parentGroup = link.closest('.nav-group');
                if (parentGroup && !parentGroup.classList.contains('open')) {
                  parentGroup.classList.add('open');
                  const b = parentGroup.querySelector('.nav-cat');
                  if (b) b.setAttribute('aria-expanded', 'true');
                }
              }
            });
          }
        });
      }, { rootMargin: '-15% 0px -75% 0px' });

      document.querySelectorAll('.screen').forEach(screen => obs.observe(screen));
    }

    function escapeRegExp(str) {
      return str.replace(/[-\/\^$*+?.()|[\]{}]/g, '\$&');
    }

    function performSearch() {
      if (!searchInput) return;
      const query = searchInput.value.trim().toLowerCase();
      let totalMatchCount = 0;

      if (!query) {
        if (searchEmpty) searchEmpty.style.display = 'none';
        groups.forEach(group => {
          group.style.display = '';
          group.querySelectorAll('.nav-sub a').forEach(a => {
            a.style.display = '';
            if (a.dataset.originalText) {
              a.innerHTML = a.dataset.originalText;
            }
          });
        });
        return;
      }

      groups.forEach(group => {
        const catTextEl = group.querySelector('.nav-cat-text');
        const catTitle = catTextEl ? catTextEl.textContent.toLowerCase() : '';
        const isCatMatch = catTitle.includes(query);
        let matchedInGroup = 0;

        const subLinks = group.querySelectorAll('.nav-sub a');
        subLinks.forEach(a => {
          if (!a.dataset.originalText) {
            a.dataset.originalText = a.textContent;
          }
          const text = a.dataset.originalText;
          const textLower = text.toLowerCase();

          if (isCatMatch || textLower.includes(query)) {
            a.style.display = '';
            matchedInGroup++;
            totalMatchCount++;

            if (query && textLower.includes(query)) {
              try {
                const regex = new RegExp('(' + escapeRegExp(query) + ')', 'gi');
                a.innerHTML = text.replace(regex, '<mark class="search-highlight">$1</mark>');
              } catch (err) {
                a.innerHTML = text;
              }
            } else {
              a.innerHTML = text;
            }
          } else {
            a.style.display = 'none';
          }
        });

        if (isCatMatch || matchedInGroup > 0) {
          group.style.display = '';
          group.classList.add('open');
          const b = group.querySelector('.nav-cat');
          if (b) b.setAttribute('aria-expanded', 'true');
        } else {
          group.style.display = 'none';
        }
      });

      if (searchEmpty) {
        searchEmpty.style.display = totalMatchCount > 0 ? 'none' : 'block';
      }
    }

    if (searchInput) {
      searchInput.addEventListener('input', performSearch);
      searchInput.addEventListener('keyup', performSearch);
    }

    if (searchClear) {
      searchClear.addEventListener('click', () => {
        searchInput.value = '';
        performSearch();
        searchInput.focus();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initManualNav);
  } else {
    initManualNav();
  }
})();
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

    nav = [f'<div class="brand">{html.escape(TITLE)}</div>'
           f'<div class="brand-sub">{html.escape(SUBTITLE)}</div>']
    search_ui = '''
<div class="nav-search">
  <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="11" cy="11" r="8"></circle>
    <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
  </svg>
  <input type="text" id="menu-search-input" placeholder="메뉴 검색 (예: 부가세, 급여)" aria-label="메뉴 검색">
  <button type="button" id="search-clear-btn" class="search-clear" aria-label="검색어 지우기">&times;</button>
</div>
<div id="search-empty" class="search-empty">검색 결과가 없습니다.</div>
'''
    nav.append(search_ui)

    if commons:
        c_links = "".join(f'<a href="#{anchor(cid)}">{html.escape(c["doc_name"])}</a>' for cid, c in commons.items())
        nav.append(f'''
<div class="nav-group open">
  <button type="button" class="nav-cat" aria-expanded="true">
    <span class="nav-cat-info">
      <span class="nav-cat-text">공통</span>
      <span class="nav-cat-badge">{len(commons)}</span>
    </span>
    <svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
  </button>
  <div class="nav-sub">{c_links}</div>
</div>''')

    for top, items in groups.items():
        s_links = "".join(f'<a href="#{anchor(sc["screen_id"])}">{html.escape(sc["screen_name"])}</a>' for sc in items)
        nav.append(f'''
<div class="nav-group open">
  <button type="button" class="nav-cat" aria-expanded="true">
    <span class="nav-cat-info">
      <span class="nav-cat-text">{html.escape(top)}</span>
      <span class="nav-cat-badge">{len(items)}</span>
    </span>
    <svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
  </button>
  <div class="nav-sub">{s_links}</div>
</div>''')

    body = [common_html(c) for c in commons.values()]
    body += [screen_html(sc, commons) for sc in screens]

    doc = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(TITLE)}</title>
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
