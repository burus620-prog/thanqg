#!/usr/bin/env python3
"""아파트ok 매뉴얼 캡처 — routes.yaml을 따라 화면을 돌며 스크린샷을 저장한다.

  준비
    pip install playwright pyyaml
    playwright install chromium
    계정은 환경변수로 넘긴다. 변수 이름은 routes.yaml 의 login.env_id / env_pw 에서 정한다.

  실행
    python3 capture.py                  # 전체 촬영. 안전 모드
    python3 capture.py --only rpt       # 화면 id 에 rpt 가 든 것만 촬영
    python3 capture.py --headed   # 브라우저를 눈으로 보며 실행
    python3 capture.py --allow-write   # 차단 해제 (테스트 단지에서만)

  안전장치
    1. 기본값에서 GET 이외의 모든 요청을 막는다. 실수로 저장 버튼을 눌러도
       서버까지 가지 않는다. 실서비스 계정 사고를 막는 마지막 방어선이다.
    2. 누르면 안 되는 버튼 이름을 목록으로 두고, 클릭 대상이 걸리면 중단한다.
    3. 시계를 고정한다. 접수일시 같은 자동 입력 필드가 매번 달라지면
       이미지 비교로 UI 변경을 감지할 수 없다.
    4. 이름·연락처·동호수로 보이는 영역을 흐리게 처리한 뒤 촬영한다.
"""
import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent
# routes.yaml 과 같은 폴더에 src 가 있으면 그 폴더 기준, 아니면 한 단계 위 기준
_ROOT = BASE if (BASE / "src").is_dir() else BASE.parent
OUT = _ROOT / "captures"
VIEWPORT = {"width": 1920, "height": 1080}
FIXED_TIME = "2026-01-02T09:00:00"  # 시계 고정값

# 절대 누르지 않는다. 저장·삭제·발송 계열.
FORBIDDEN = {"저장", "삭제", "결재요청", "상신", "발송", "전송", "송출", "탈퇴하기"}

# 개인정보로 보이는 영역을 가리는 CSS.
# 서비스가 연락처 가운데 자리는 이미 가리고 있어 이름 위주로 처리한다.
MASK_CSS = """
.mask-pii, [data-pii] { filter: blur(5px) !important; }
"""
# 화면 구조를 몰라도 자료 영역을 가린다.
# 표의 제목 줄은 남기고 내용 줄만 흐리게 해서, 무엇이 나오는 화면인지는 보이되
# 거래처·금액·번호는 읽히지 않게 한다.
MASK_DATA_JS = r"""
([maskCols, maskIds, defaultKeep]) => {
  if (!document || !document.body) return 0;
  let n = 0;
  const DEFAULT_KEEP = defaultKeep || 3;
  // "이름" 또는 "이름:글자수" 형태를 받는다. 글자수를 안 적으면 기본값을 쓴다.
  const COLS = (maskCols || []).map(s => {
    const parts = String(s).split(':');
    return { k: parts[0].replace(/\s+/g, ''),
             keep: parts[1] ? parseInt(parts[1], 10) : DEFAULT_KEEP };
  });
  const colKeep = (headerText) => {
    const hit = COLS.find(c => headerText.includes(c.k));
    return hit ? hit.keep : null;
  };

  const DOT  = '●';
  const ID_PAT   = /(\d{3}-\d{2}-\d{5})|(\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{0,4})/;
  const DATE_PAT = /^\s*\d{2,4}[-./]\d{1,2}([-./]\d{1,2})?\s*$/;
  const SKIP_TAG = new Set(['SCRIPT','STYLE','SELECT','OPTION','TEXTAREA']);

  const veil = (s, keep) => {
    const K = (keep === null || keep === undefined) ? DEFAULT_KEEP : keep;
    const v = s.trim();
    if (!v) return s;
    if (ID_PAT.test(v)) return DOT.repeat(Math.min(v.length, 12));
    if (v.length <= K) return v;
    return v.slice(0, K) + DOT.repeat(Math.min(v.length - K, 12));
  };

  // 칸 안의 글자 조각을 직접 바꾼다. 아이콘과 섞여 있어도 빠지지 않는다.
  const maskInside = (root, keep) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => {
        const p = node.parentElement;
        if (!p || SKIP_TAG.has(p.tagName)) return NodeFilter.FILTER_REJECT;
        return node.nodeValue && node.nodeValue.trim()
               ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      const v = node.nodeValue;
      if (DATE_PAT.test(v)) return;
      const m = veil(v, keep);
      if (m !== v.trim()) { node.nodeValue = m; n++; }
    });
  };

  const EMPTY_PAT = /없습니다|없음|없슴|no\s*data|조회된|검색된|결과가 없|내역이 없|자료가 없/;
  const isEmptyRow = (row) => {
    const txt = (row.textContent || '').trim();
    if (!txt) return true;
    if (EMPTY_PAT.test(txt)) return true;
    const cells = row.querySelectorAll('td,th');
    if (cells.length === 1 && cells[0].hasAttribute('colspan')) return true;
    return false;
  };

  const colCount = (row) => {
    let c = 0;
    row.querySelectorAll(':scope > td, :scope > th').forEach(x => {
      c += parseInt(x.getAttribute('colspan') || '1', 10);
    });
    return c;
  };

  const ownHeaderRow = (table) => {
    let best = null, cnt = 0;
    table.querySelectorAll('tr').forEach(tr => {
      const c = tr.querySelectorAll('th').length;
      if (c > cnt) { cnt = c; best = tr; }
    });
    return best;
  };

  // 열을 고정한 화면은 제목 표와 내용 표가 나뉜다. 같은 상자에서 빌려온다.
  const borrowedHeader = (table) => {
    const first = table.querySelector('tr');
    if (!first) return null;
    const want = colCount(first);
    let scope = table.parentElement;
    for (let up = 0; up < 4 && scope; up++, scope = scope.parentElement) {
      const rows = Array.from(scope.querySelectorAll('tr'))
        .filter(tr => tr.querySelectorAll('th').length > 0 && !table.contains(tr));
      const hit = rows.find(tr => colCount(tr) === want);
      if (hit) return hit;
    }
    return null;
  };

  // 가릴 열의 번호. 제목 줄 이름이 목록에 걸리는 열만 고른다.
  const maskIndexes = (table) => {
    const map = new Map();          // 열 번호 → 남길 글자 수
    const head = ownHeaderRow(table) || borrowedHeader(table);
    if (!head) return map;
    let idx = 0;
    Array.from(head.querySelectorAll('th,td')).forEach(th => {
      const span = parseInt(th.getAttribute('colspan') || '1', 10);
      const h = (th.textContent || '').replace(/\s+/g, '');
      const keep = colKeep(h);
      if (keep !== null) {
        for (let i = 0; i < span; i++) map.set(idx + i, keep);
      }
      idx += span;
    });
    return map;
  };

  const maskRow = (row, targets) => {
    if (!targets.size) return;
    if (isEmptyRow(row)) return;
    const cells = row.querySelectorAll(':scope > td, :scope > th');
    let idx = 0;
    Array.from(cells).forEach(td => {
      const span = parseInt(td.getAttribute('colspan') || '1', 10);
      let keep = null;
      for (let i = 0; i < span; i++) if (targets.has(idx + i)) keep = targets.get(idx + i);
      if (keep !== null) maskInside(td, keep);
      idx += span;
    });
  };

  // 표
  document.querySelectorAll('table').forEach(tb => {
    const own = ownHeaderRow(tb);
    const rows = Array.from(tb.querySelectorAll('tr')).filter(r => r !== own);
    if (!rows.some(r => !isEmptyRow(r))) return;
    const targets = maskIndexes(tb);
    rows.forEach(r => maskRow(r, targets));
  });

  // div 로 만든 표 — 바로 위 상자의 제목에 걸릴 때만
  document.querySelectorAll(
    '[role=row], .grid-row, .gridRow, .row-data, .dataRow').forEach(row => {
      if (row.querySelector('th')) return;
      if (isEmptyRow(row)) return;
      const box = row.parentElement;
      const head = box && box.querySelector('[role=columnheader], th, .grid-header');
      if (!head) return;
      const h = (head.textContent || '').replace(/\s+/g, '');
      const keep = colKeep(h);
      if (keep !== null) maskInside(row, keep);
  });

  // 입력칸 — 항목명·안내문구·라벨에 목록의 이름이 있을 때만
  const around = (el) => {
    const bits = [el.name, el.id, el.placeholder, el.title,
                  el.getAttribute && el.getAttribute('aria-label')];
    const lab = el.closest('label') ||
                (el.id && document.querySelector(`label[for="${el.id}"]`));
    if (lab) bits.push(lab.textContent);
    const cell = el.closest('td,div,li');
    if (cell && cell.previousElementSibling) bits.push(cell.previousElementSibling.textContent);
    const th = el.closest('tr') && el.closest('tr').querySelector('th');
    if (th) bits.push(th.textContent);
    return bits.filter(Boolean).join(' ').replace(/\s+/g, '');
  };

  document.querySelectorAll('input,textarea').forEach(el => {
    const v = (el.value || '').trim();
    const type = (el.type || '').toLowerCase();
    if (!v || ['date','checkbox','radio','button','submit','hidden'].includes(type)) return;
    if (DATE_PAT.test(v)) return;
    const ctx = around(el);
    const keep = colKeep(ctx);
    if (keep === null) return;
    el.value = veil(v, keep);
    n++;
  });

  // 사업자등록번호·카드번호는 열과 무관하게 가린다 (mask_id_numbers 로 끌 수 있다)
  if (maskIds) {
    document.querySelectorAll('td,span,div,p,li,strong,b,em').forEach(el => {
      if (el.children.length === 0 && ID_PAT.test(el.textContent || '')) maskInside(el, 0);
    });
  }

  return n;
}
"""

MASK_JS = r"""
() => {
  if (!document || !document.body) return;
  const pat = /(01[016-9]-?\d{3,4}-?\d{4})|(제?\s?\d{1,3}동\s?\d{1,4}호)/;
  const skip = new Set(['SCRIPT','STYLE','HEAD']);
  const walk = (el) => {
    for (const n of el.children) {
      if (skip.has(n.tagName)) continue;
      if (n.children.length === 0 && pat.test(n.textContent || '')) {
        n.classList.add('mask-pii');
      } else walk(n);
    }
  };
  walk(document.body);
}
"""


def load_routes():
    raw = open(BASE / "routes.yaml", encoding="utf-8").read()
    # ${VAR} 를 환경변수로 치환한다. 실명 같은 값을 파일에 적지 않기 위한 것.
    for key in set(re.findall(r"\$\{(\w+)\}", raw)):
        val = os.getenv(key)
        if not val:
            sys.exit(f"환경변수 {key} 가 필요합니다. routes.yaml 에서 참조하고 있습니다.")
        raw = raw.replace("${%s}" % key, val)
    return yaml.safe_load(raw)


def close_modal(page, label, log):
    """안내창의 버튼을 누른다. 버튼 → 텍스트 순으로 여러 방법을 시도한다."""
    tries = [
        lambda: page.get_by_role("button", name=label).first,
        lambda: page.locator(f"button:has-text('{label}')").first,
        lambda: page.locator(f".modal :text-is('{label}'), "
                             f"[class*=modal] :text-is('{label}'), "
                             f"[class*=popup] :text-is('{label}')").first,
        lambda: page.get_by_text(label, exact=True).last,
    ]
    for i, get in enumerate(tries, 1):
        try:
            el = get()
            el.wait_for(state="visible", timeout=2500)
            el.click()
            page.wait_for_timeout(700)
            if not modal_open(page):
                log.append(f"  · 안내창 닫음 ({i}번째 방법)")
                return True
        except Exception:
            continue
    log.append(f"  X 안내창의 [{label}] 을 누르지 못했습니다. 창이 열린 채로 남았습니다")
    return False


def click_row(page, n, log):
    """목록 표의 n번째 데이터 행을 연다. 읽기 동작이므로 안전하다."""
    try:
        page.locator("table tbody tr").nth(int(n) - 1).click(timeout=8000)
        page.wait_for_timeout(700)
        return True
    except Exception as e:
        log.append(f"  X {n}번째 행 클릭 실패 — {type(e).__name__}")
        return False


def guard(label):
    if label.strip() in FORBIDDEN:
        sys.exit(f"[중단] 누르면 안 되는 버튼입니다: {label}")


JS_CLICK = r"""
([label, within]) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const all = Array.from(document.querySelectorAll('*'));
  const txt = e => norm(e.textContent) || norm(e.value) ||
                  norm(e.getAttribute && (e.getAttribute('title') ||
                       e.getAttribute('aria-label')));
  let hits = all.filter(e => txt(e) === label);
  if (within) {
    hits = hits.filter(e => {
      let p = e.parentElement;
      while (p) { if (norm(p.textContent).includes(within)) return true; p = p.parentElement; }
      return false;
    });
  }
  if (!hits.length) return 'notfound';
  // 같은 글자를 가진 것 중 가장 안쪽 요소를 고른다
  hits.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
  let el = hits[0];
  const clickable = el.closest('a,button,li,tr,td,[onclick],[role=button]');
  (clickable || el).scrollIntoView({block: 'center'});
  (clickable || el).click();
  return 'ok';
}
"""


JS_SCOPED_CLICK = r"""
([label, within]) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const bare = s => (s || '').replace(/\s+/g, '');
  const L = bare(label), W = bare(within);
  const all = Array.from(document.querySelectorAll('*'));
  // 그룹 이름과 항목 이름을 둘 다 품은 상자들 중 가장 작은 것
  let boxes = all.filter(e => {
    const b = bare(e.textContent);
    return b.includes(W) && b.includes(L);
  });
  if (!boxes.length) return 'noscope';
  boxes.sort((a, b) => bare(a.textContent).length - bare(b.textContent).length);
  const box = boxes[0];
  // 그 안에서 항목 이름과 정확히 같은 가장 안쪽 요소
  let hits = Array.from(box.querySelectorAll('*')).filter(e => bare(e.textContent) === L);
  if (!hits.length) return 'nohit';
  hits.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
  const el = hits[0];
  const clickable = el.closest('a,button,li,tr,td,[onclick],[role=button]') || el;
  clickable.scrollIntoView({block: 'center'});
  clickable.click();
  return 'ok';
}
"""


def in_scope(page, within):
    """제목 글자가 들어 있는 가장 안쪽 상자를 찾아 그 안에서만 찾도록 한다."""
    try:
        box = page.locator(
            f"div:has-text('{within}'), section:has-text('{within}'), "
            f"ul:has-text('{within}')").last
        box.wait_for(state="attached", timeout=3000)
        return box
    except Exception:
        return None


def click(page, kind, label, log, within=None):
    """상단/좌측/탭/일반 텍스트를 클릭한다. 링크가 javascript:; 라 텍스트로 찾는다."""
    guard(label)

    # 1) within 이 지정되면 그룹 이름과 항목 이름을 함께 품은 가장 작은 상자에서 찾는다.
    #    같은 이름이 다른 묶음에도 있을 때 이 방법만 정확하다.
    if within:
        try:
            r = page.evaluate(JS_SCOPED_CLICK, [label, within])
            if r == "ok":
                page.wait_for_timeout(800)
                return True
            log.append(f"  ! '{within}' 안에서 '{label}' 을 못 찾음 ({r}) — 다른 방법 시도")
        except Exception:
            pass
        box = in_scope(page, within)
        if box:
            try:
                t = box.get_by_text(label, exact=True).last
                t.wait_for(state="visible", timeout=4000)
                t.click()
                page.wait_for_timeout(700)
                return True
            except Exception:
                pass

    # 2) 버튼으로 찾는다. <input type=button value="..."> 처럼
    #    글자가 아니라 값으로 이름을 갖는 요소가 여기서 잡힌다
    for get in (
        lambda: page.get_by_role("button", name=label, exact=True).first,
        lambda: page.locator(f"input[value='{label}']").first,
        lambda: page.locator(f"[title='{label}'], [aria-label='{label}']").first,
    ):
        try:
            el = get()
            el.wait_for(state="visible", timeout=3000)
            el.click()
            page.wait_for_timeout(700)
            return True
        except Exception:
            continue

    # 3) 화면 전체에서 글자로 찾는다. 뒤쪽에 있는 것이 대개 본문이다
    for pick in ("last", "first"):
        try:
            t = getattr(page.get_by_text(label, exact=True), pick)
            t.wait_for(state="visible", timeout=4000)
            t.click()
            page.wait_for_timeout(700)
            return True
        except Exception:
            continue

    # 3.5) 띄어쓰기만 다른 경우를 위해 공백을 무시하고 찾는다.
    #      같은 메뉴가 화면마다 '거래(전표)입력' / '거래(전표) 입력' 으로 다르게 쓰인다.
    bare = re.sub(r"\s+", "", label)
    if bare != label or " " in label:
        try:
            rx = re.compile(r"^\s*" + r"\s*".join(re.escape(c) for c in bare) + r"\s*$")
            el = page.get_by_text(rx).last
            el.wait_for(state="visible", timeout=3000)
            el.click()
            page.wait_for_timeout(700)
            log.append(f"  ! '{label}' 은 띄어쓰기를 무시하고 찾았습니다")
            return True
        except Exception:
            pass

    # 4) 마지막 수단 — 브라우저 안에서 직접 찾아 누른다
    try:
        r = page.evaluate(JS_CLICK, [label, within])
        if r == "ok":
            page.wait_for_timeout(800)
            log.append(f"  ! '{label}' 은 직접 클릭으로 처리했습니다")
            return True
    except Exception:
        pass

    log.append(f"  X '{label}' 클릭 실패 — 화면에서 찾지 못했습니다")
    try:
        near = page.evaluate(r"""
        (label) => {
          const norm = s => (s || '').replace(/\s+/g, ' ').trim();
          const out = [];
          for (const e of document.querySelectorAll('input,button,a,li,td,span,div')) {
            const v = norm(e.textContent) || norm(e.value) || '';
            if (v && v.length < 30 && (v.includes(label.slice(0, 3)) ||
                label.includes(v.slice(0, 3)))) {
              out.push(e.tagName.toLowerCase() +
                       (e.type ? '[' + e.type + ']' : '') + ' = ' + v);
            }
            if (out.length > 6) break;
          }
          return out;
        }""", label)
        if near:
            log.append("    비슷한 요소: " + " / ".join(near))
    except Exception:
        pass
    return False


def modal_open(page):
    """화면을 덮는 안내창이 떠 있는지 본다. 이게 열려 있으면 이후 클릭이 모두 막힌다."""
    for sel in (".modal:visible", ".layer:visible", ".popup:visible",
                "[class*=modal]:visible", "[class*=popup]:visible"):
        try:
            if page.locator(sel).first.is_visible():
                return True
        except Exception:
            pass
    return False


URLS = {}            # 촬영에 성공한 화면의 주소. 다음 실행에서 주소 이동에 쓴다
MASK_DATA = True     # routes.yaml 의 mask_data 로 끌 수 있다
MASK_COLS = []       # 가릴 열 이름 (routes.yaml 의 mask_columns)
MASK_IDS = True      # 사업자등록번호·카드번호 가리기
MASK_KEEP_CHARS = 3  # 앞에서 남길 글자 수 (열마다 다르게 줄 수 있다)


def shot(page, name, screen_id, expect, masks, seen, log):
    """촬영하되, 의도한 화면인지 검증한다. 검증에 실패하면 성공으로 세지 않는다."""
    if expect:
        try:
            page.get_by_text(expect, exact=False).first.wait_for(
                state="visible", timeout=6000)
        except Exception:
            log.append(f"  X {name} — '{expect}' 가 화면에 없습니다. 다른 화면입니다")
            return False

    try:
        page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass

    masked = True
    for step in (lambda: page.add_style_tag(content=MASK_CSS),
                 lambda: page.evaluate(MASK_JS)):
        try:
            step()
        except Exception:
            masked = False
    if MASK_DATA:
        try:
            cnt = page.evaluate(MASK_DATA_JS, [MASK_COLS, MASK_IDS, MASK_KEEP_CHARS])
            if cnt:
                log.append(f"    자료 {cnt}칸 가림")
        except Exception:
            masked = False
    for sel in masks:
        try:
            page.eval_on_selector_all(
                sel, "els => els.forEach(e => e.classList.add('mask-pii'))")
        except Exception:
            pass
    if not masked:
        log.append(f"  ! {name} — 마스킹을 적용하지 못했습니다. "
                   f"개인정보가 보이는지 반드시 확인하세요")

    path = OUT / screen_id / name
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception as e:
        log.append(f"  X {name} — 촬영 실패 ({type(e).__name__})")
        return False

    url = page.url
    digest = hashlib.md5(path.read_bytes()).hexdigest()
    if digest in seen:
        prev, prev_url = seen[digest]
        log.append(f"  X {name} — 앞서 찍은 {prev} 와 완전히 같습니다. "
                   f"화면이 바뀌지 않았습니다")
        if url == prev_url:
            log.append(f"    주소도 같습니다 ({url[-45:]}) — 메뉴 클릭이 먹지 않았습니다")
        else:
            log.append(f"    주소는 다릅니다 ({url[-45:]}) — 화면은 갔는데 내용이 같습니다")
        try:
            path.rename(path.with_name(path.stem + "_확인필요.png"))
            log.append(f"    확인용으로 남겨둠: {path.stem}_확인필요.png")
        except Exception:
            pass
        return False
    seen[digest] = (name, url)
    URLS[screen_id] = url
    log.append(f"  · {name}")
    return True


def run(args):
    cfg = load_routes()
    # 계정 환경변수 이름은 routes.yaml 에서 정한다. 서비스마다 다르게 쓸 수 있다.
    lg0 = cfg.get("login", {})
    k_id = lg0.get("env_id", "MANUAL_ID")
    k_pw = lg0.get("env_pw", "MANUAL_PW")
    uid, pw = os.getenv(k_id), os.getenv(k_pw)
    if not uid or not pw:
        sys.exit(f"{k_id} / {k_pw} 환경변수를 설정하세요. 코드에 계정을 적지 마세요.\n"
                 f"  PowerShell:  $env:{k_id}=\"아이디\"\n"
                 f"               $env:{k_pw}=\"비밀번호\"")

    log, made, failed = [], 0, []
    blocked_own = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        ctx = browser.new_context(viewport=VIEWPORT, locale="ko-KR",
                                  timezone_id="Asia/Seoul")

        # 이 서비스처럼 조회도 POST 로 하는 곳이 있다.
        # routes.yaml 의 allow_post 에 적힌 조각이 주소에 들어 있으면 통과시킨다.
        allow = [str(x) for x in cfg.get("allow_post", [])]
        deny = [str(x) for x in cfg.get("deny_post", [])]

        # 서비스 자기 주소가 아닌 곳(광고·분석·상담 도구)은 무조건 막는다
        from urllib.parse import urlparse
        site_host = urlparse(cfg["login"]["url"]).hostname or ""

        blocked_own = set()
        READ_HINTS = ("list", "data", "search", "view", "get", "inquiry",
                      "summary", "detail", "select", "find")

        def is_read(url):
            low = url.lower()
            if (urlparse(url).hostname or "") != site_host:
                return False
            if any(d.lower() in low for d in deny):
                return False
            if any(a.lower() in low for a in allow):
                return True
            # 통과는 아니지만 조회처럼 보이면 나중에 알려주기 위해 모아둔다
            if any(h in low for h in READ_HINTS):
                blocked_own.add(url.split("?")[0].rsplit("/", 1)[-1])
            return False

        if not args.allow_write:
            def block(route, request):
                if request.method != "GET":
                    if is_read(request.url):
                        return route.continue_()
                    log.append(f"  [차단] {request.method} {request.url[:70]}")
                    return route.abort()
                route.continue_()
            ctx.route("**/*", block)

        page = ctx.new_page()
        page.clock.set_fixed_time(FIXED_TIME)

        # 로그인 — 로그인 요청은 POST이므로 차단 대상에서 잠시 제외한다.
        lg = cfg["login"]
        if not args.allow_write:
            ctx.unroute("**/*")
        page.goto(lg["url"], wait_until="domcontentloaded")
        page.wait_for_timeout(800)

        # 아이디·비밀번호 칸을 여러 방법으로 찾는다
        def fill_field(selectors, value, what):
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    el.wait_for(state="visible", timeout=3000)
                    el.fill(value)
                    return True
                except Exception:
                    continue
            log.append(f"  X {what} 입력칸을 찾지 못했습니다")
            return False

        ok_id = fill_field([lg.get("id_field", ""), "input[type=text]",
                            "input[type=email]", "input[name*=id i]",
                            "input:not([type=password]):not([type=hidden]):not([type=checkbox])"],
                           uid, "아이디")
        ok_pw = fill_field([lg.get("pw_field", ""), "input[type=password]"],
                           pw, "비밀번호")

        # 로그인 버튼도 여러 방법으로 누른다. 같은 글자의 제목을 누르면 아무 일도 안 난다.
        label = lg.get("submit", "로그인")
        before = page.url
        pressed = False
        for get in (
            lambda: page.get_by_role("button", name=label).first,
            lambda: page.locator(f"input[type=submit][value='{label}']").first,
            lambda: page.locator(f"button:has-text('{label}')").first,
            lambda: page.locator("form input[type=submit], form button").first,
            lambda: page.get_by_text(label, exact=True).last,
        ):
            try:
                el = get()
                el.wait_for(state="visible", timeout=2500)
                el.click()
                pressed = True
                break
            except Exception:
                continue
        if not pressed and ok_pw:
            try:
                page.locator(lg.get("pw_field", "input[type=password]")).first.press("Enter")
                pressed = True
            except Exception:
                pass

        page.wait_for_timeout(2500)

        # 성공 판정 — 판정 문구가 보이거나, 주소가 로그인 화면에서 벗어나면 성공
        ready = lg.get("ready")
        signed_in = False
        if ready:
            for probe in (ready, ready.replace(" ", ""), ready[:4]):
                try:
                    page.get_by_text(probe, exact=False).first.wait_for(timeout=6000)
                    signed_in = True
                    break
                except Exception:
                    continue
        if not signed_in and page.url != before and "login" not in page.url.lower():
            signed_in = True
            log.append("  ! 판정 문구는 못 찾았지만 주소가 바뀌어 로그인된 것으로 봅니다")

        if not signed_in:
            log.append("\n로그인 실패. 아래를 확인하세요.")
            log.append(f"  현재 주소 : {page.url}")
            log.append(f"  아이디 칸 : {'입력됨' if ok_id else '못 찾음'} / "
                       f"비밀번호 칸 : {'입력됨' if ok_pw else '못 찾음'} / "
                       f"버튼 : {'눌림' if pressed else '못 누름'}")
            try:
                txt = page.evaluate(
                    "() => (document.body ? document.body.innerText : '')"
                    ".replace(/\\s+/g,' ').trim().slice(0, 300)")
                log.append(f"  화면 글자 : {txt}")
            except Exception:
                pass
            try:
                page.screenshot(path=str(OUT / "_login_failed.png"))
                log.append(f"  화면 저장 : {OUT / '_login_failed.png'}")
            except Exception:
                pass
            print("\n".join(log))
            browser.close()
            return 1

        log.append("로그인 완료")

        # 로그인 후 단지 선택 화면이 뜨는 경우
        if cfg["login"].get("complex"):
            try:
                page.get_by_text(cfg["login"]["complex"], exact=False).first.click(
                    timeout=4000)
                page.wait_for_timeout(1500)
                log.append(f"단지 선택: {cfg['login']['complex']}")
            except Exception:
                pass

        if not args.allow_write:
            def block2(route, request):
                if request.method != "GET":
                    if is_read(request.url):
                        return route.continue_()
                    log.append(f"  [차단] {request.method} {request.url[:70]}")
                    return route.abort()
                route.continue_()
            ctx.route("**/*", block2)

        global MASK_DATA, MASK_COLS, MASK_IDS, MASK_KEEP_CHARS
        MASK_DATA = bool(cfg.get("mask_data", True))
        MASK_COLS = [str(x) for x in cfg.get("mask_columns", [])]
        MASK_IDS = bool(cfg.get("mask_id_numbers", True))
        globals()["MASK_KEEP_CHARS"] = int(cfg.get("mask_keep_chars", 3))
        if MASK_DATA:
            log.append(f"가릴 열: {', '.join(MASK_COLS) if MASK_COLS else '(없음)'}"
                       f" · 사업자·카드번호: {'가림' if MASK_IDS else '안 가림'}")
        if not MASK_DATA:
            log.append("\n! 자료 가리기가 꺼져 있습니다. 촬영본에 실제 거래 자료가 그대로 남습니다")

        seen = {}
        masks_global = cfg.get("mask_global", [])

        picked = [r for r in cfg["routes"]
                  if not args.only or args.only in r["screen_id"]]
        if args.only:
            log.append(f"'{args.only}' 이 들어간 화면 {len(picked)}개만 촬영합니다")

        for route in picked:
          try:
            sid = route["screen_id"]
            masks = masks_global + route.get("mask", [])
            log.append(f"\n▶ {sid}")
            ok = True
            expecting_modal = False
            for step in route["steps"]:
                if "shot" in step:
                    name = step["shot"]
                    if not ok:
                        failed.append(name)
                        continue
                    try:
                        good = shot(page, name, sid, step.get("expect"),
                                    masks, seen, log)
                    except Exception as e:
                        log.append(f"  X {name} — 촬영 중 오류 ({type(e).__name__})")
                        good = False
                    if good:
                        made += 1
                    else:
                        failed.append(name)
                        ok = False
                    continue

                kind = next(k for k in step if k != "within")
                val = step[kind]

                if kind == "wait":
                    page.wait_for_timeout(int(val))
                    continue

                if kind == "url":
                    # 주소로 바로 이동한다. 클릭보다 빠르고 잘 안 깨진다.
                    try:
                        page.goto(str(val), wait_until="domcontentloaded",
                                  timeout=15000)
                        page.wait_for_timeout(800)
                    except Exception as e:
                        log.append(f"  X {val} 열기 실패 ({type(e).__name__})")
                        ok = False
                    continue

                if kind == "expect_modal":
                    # 여기서 안내창이 뜨는 것이 정상이다. 뜨지 않으면 오히려 실패.
                    try:
                        page.get_by_text(str(val), exact=False).first.wait_for(
                            state="visible", timeout=6000)
                        expecting_modal = True
                        log.append(f"  · 안내창 확인: {val}")
                    except Exception:
                        log.append(f"  X '{val}' 안내창이 뜨지 않았습니다")
                        ok = False
                    continue

                if kind == "close_modal":
                    ok = close_modal(page, str(val), log) and ok
                    expecting_modal = False
                    continue

                if kind == "selector":
                    # 글자가 없는 아이콘처럼 CSS 로만 집을 수 있는 것
                    try:
                        el = page.locator(str(val)).first
                        el.wait_for(state="visible", timeout=6000)
                        el.click()
                        page.wait_for_timeout(800)
                    except Exception as e:
                        log.append(f"  X 선택자 '{val}' 클릭 실패 ({type(e).__name__})")
                        ok = False
                    continue

                if kind == "nth_row":
                    ok = click_row(page, val, log) and ok
                else:
                    ok = click(page, kind, str(val), log,
                               step.get("within")) and ok

                # 예상하지 않은 안내창이 뜨면 이후 클릭이 전부 막힌다. 여기서 끊는다.
                if ok and not expecting_modal and modal_open(page):
                    log.append("  ! 예상하지 못한 안내창이 떠 있습니다. 여기서 멈춥니다")
                    log.append("    창 문구를 확인하고, 매뉴얼에 필요한 화면이면 "
                               "routes.yaml 에 expect_modal 과 close_modal 을 넣으세요")
                    ok = False
            if not ok:
                log.append(f"  → {sid} 중단됨")
            # 다음 경로가 오염되지 않도록 화면을 처음 상태로 되돌린다
            if modal_open(page):
                for label in ("확인", "닫기", "취소"):
                    if close_modal(page, label, log):
                        break
          except Exception as e:
            log.append(f"  X {route.get('screen_id')} 경로에서 오류 "
                       f"({type(e).__name__}). 다음 경로로 넘어갑니다")

        try:
            browser.close()
        except Exception:
            pass

    print("\n".join(log))
    print(f"\n촬영 {made}장 · 실패 {len(failed)}장 · 저장 위치 {OUT}")
    if URLS:
        import json as _json
        up = OUT / "_urls.json"
        try:
            up.parent.mkdir(parents=True, exist_ok=True)
            _json.dump(URLS, open(up, "w", encoding="utf-8"),
                       ensure_ascii=False, indent=2)
            print(f"\n화면 주소 {len(URLS)}개를 {up.name} 에 기록했습니다.")
            print("  주소가 화면마다 다르면, routes.yaml 의 클릭 단계를")
            print("  '- url: 주소' 로 바꾸는 편이 훨씬 안정적입니다.")
        except Exception:
            pass

    if blocked_own:
        print("\n조회로 보이는데 차단된 요청이 있습니다. 화면에 자료가 비어 있을 수 있습니다.")
        for name in sorted(blocked_own):
            print(f"  · {name}")
        print("  → routes.yaml 의 allow_post 에 위 이름의 일부를 추가한 뒤 다시 촬영하세요.")
    if failed:
        print("실패한 이미지: " + ", ".join(failed))
        print("클릭 대상을 못 찾은 것이므로, 화면이 바뀌었는지 확인하고 routes.yaml을 고치세요.")
    return 1 if failed else 0


def audit():
    """원본이 요구하는 이미지 / 경로에 정의된 이미지 / 실제 파일 세 가지를 대조한다."""
    want = set()
    files, seen = [], set()
    for folder in (_ROOT / "src", _ROOT):
        if not folder.is_dir():
            continue
        for f0 in sorted(folder.glob("*.yaml")):
            if f0.name in {"routes.yaml", "site.yaml"} or f0.name in seen:
                continue
            seen.add(f0.name)
            files.append(f0)
    for f in files:
        for doc in yaml.safe_load_all(open(f, encoding="utf-8")):
            for item in doc or []:
                for s in item.get("steps", []):
                    if s.get("image"):
                        want.add(s["image"])
                for sf in item.get("sub_flows", []):
                    for s in sf["steps"]:
                        if s.get("image"):
                            want.add(s["image"])

    raw = open(BASE / "routes.yaml", encoding="utf-8").read()
    # 주석 줄은 세지 않는다 (설명용 예시가 섞이는 것을 막는다)
    body = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("#"))
    planned = set(re.findall(r"shot:\s*(\S+\.png)", body))
    have = {p.name for p in OUT.rglob("*.png")}

    print(f"원본 요구 {len(want)}장 · 경로 정의 {len(planned)}장 · 실제 파일 {len(have)}장\n")

    problems = 0
    for title, missing in [
        ("경로에 빠진 이미지 (촬영 계획 없음)", sorted(want - planned)),
        ("원본에 없는 촬영 계획 (지워도 되는 것)", sorted(planned - want)),
        ("아직 안 찍힌 이미지", sorted(want & planned) if not have else sorted(want - have)),
    ]:
        if missing:
            problems += 1
            print(f"{title}: {len(missing)}장")
            print("  " + "\n  ".join(missing) + "\n")
    if not problems:
        print("모두 일치합니다.")
    return 1 if (want - planned) else 0


def safe_run(args):
    try:
        return run(args)
    except Exception as e:
        if "closed" in str(e).lower():
            print("\n브라우저 창이 닫혀 실행이 중단되었습니다. "
                  "촬영이 끝날 때까지 창을 닫지 마세요.")
            return 1
        raise


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true", help="브라우저를 화면에 띄운다")
    ap.add_argument("--allow-write", action="store_true",
                    help="쓰기 요청 차단을 푼다. 테스트 단지에서만 사용")
    ap.add_argument("--only", default=None,
                    help="화면 id 에 이 글자가 들어간 것만 촬영한다 (예: --only rpt)")
    ap.add_argument("--audit", action="store_true",
                    help="촬영하지 않고, 원본이 요구하는 이미지와 실제 파일을 대조만 한다")
    a = ap.parse_args()
    sys.exit(audit() if a.audit else safe_run(a))
