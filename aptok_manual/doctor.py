#!/usr/bin/env python3
"""무엇이 잘못됐는지 알려주는 진단 도구.

  python doctor.py

작업 폴더에 두고 실행하면, 폴더 구조를 훑어서 어디가 문제인지와
무엇을 하면 되는지를 알려준다. 아무것도 고치지 않고 읽기만 한다.

출력 결과를 그대로 복사해서 보내면 원인을 함께 볼 수 있다.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ok, warn, bad, todo = [], [], [], []


def find_dir(names, root, depth=3):
    """이름이 맞는 폴더를 위아래로 찾아본다."""
    for n in names:
        p = root / n
        if p.is_dir():
            return p
    hits = []
    for dirpath, dirs, _f in os.walk(root):
        if Path(dirpath).relative_to(root).parts.__len__() >= depth:
            dirs[:] = []
            continue
        for d in dirs:
            if d in names:
                hits.append(Path(dirpath) / d)
    return hits[0] if hits else None


def tree(root, max_depth=2, max_items=12):
    lines = []
    for dirpath, dirs, files in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        depth = len(rel.parts)
        if depth > max_depth:
            dirs[:] = []
            continue
        dirs.sort()
        indent = "  " * depth
        label = root.name if depth == 0 else rel.parts[-1]
        pngs = [f for f in files if f.lower().endswith(".png")]
        others = sorted(f for f in files if not f.lower().endswith(".png"))
        note = f"   (png {len(pngs)}장)" if pngs else ""
        lines.append(f"{indent}{label}\\{note}")
        for f in others[:max_items]:
            lines.append(f"{indent}  {f}")
        if len(others) > max_items:
            lines.append(f"{indent}  … 외 {len(others)-max_items}개")
    return "\n".join(lines)


def main():
    print("=" * 62)
    print("아파트ok 매뉴얼 작업 진단")
    print("=" * 62)
    print(f"\n실행 위치: {HERE}")
    print(f"파이썬   : {sys.version.split()[0]}\n")

    # 1. 필요한 꾸러미
    for mod, install in [("yaml", "pyyaml"), ("PIL", "pillow")]:
        try:
            __import__(mod)
            ok.append(f"{install} 설치됨")
        except ImportError:
            bad.append(f"{install} 가 없습니다")
            todo.append(f"pip install {install}")

    # 2. 폴더 구조
    print("[ 폴더 구조 ]")
    print(tree(HERE))
    print()

    src = find_dir(["src", "manual", "yaml"], HERE)
    caps = find_dir(["captures", "capture", "screenshots", "이미지"], HERE)

    if src:
        yamls = sorted(src.glob("*.yaml"))
        if yamls:
            ok.append(f"원본 폴더 {src.name}\\ 에 yaml {len(yamls)}개")
        else:
            bad.append(f"{src.name}\\ 안에 yaml 파일이 없습니다")
    else:
        bad.append("원본 폴더(src)를 못 찾았습니다")
        todo.append("hr-permission.yaml 등 yaml 파일들을 src\\ 폴더에 넣으세요")

    pngs = list(caps.rglob("*.png")) if caps else []
    if caps:
        sub = {p.parent.name for p in pngs}
        ok.append(f"캡처 폴더 {caps.name}\\ 에 png {len(pngs)}장 "
                  f"({'하위폴더 ' + str(len(sub)) + '개로 나뉨' if len(sub) > 1 else '한 폴더에 모여 있음'})")
    else:
        warn.append("캡처 폴더를 못 찾았습니다. 아직 안 찍었다면 정상입니다")

    # 3. 스크립트
    for f, why in [("build.py", "매뉴얼 생성"), ("verify.py", "캡처 검증"),
                   ("capture.py", "화면 촬영")]:
        hits = list(HERE.rglob(f))
        if hits:
            loc = hits[0].parent
            same = loc == (src.parent if src else HERE)
            ok.append(f"{f} ({why}) — {loc.name}\\ 에 있음")
            if src and loc != src.parent:
                warn.append(f"{f} 가 src\\ 의 부모 폴더가 아닌 곳에 있습니다. "
                            f"src\\ 와 captures\\ 가 있는 폴더에 두어야 합니다")
        else:
            warn.append(f"{f} 가 없습니다 ({why})")

    # 4. 원본이 요구하는 이미지와 실제 대조
    if src and pngs:
        try:
            import yaml as Y
            want = set()
            for f in src.glob("*.yaml"):
                for doc in Y.safe_load_all(open(f, encoding="utf-8")):
                    for item in doc or []:
                        flows = [item.get("steps", [])]
                        flows += [sf["steps"] for sf in item.get("sub_flows", [])]
                        for st in flows:
                            for s in st:
                                if s.get("image"):
                                    want.add(s["image"])
            have = {p.name for p in pngs}
            miss = want - have
            if not want:
                warn.append("yaml 안에 image 항목이 없습니다")
            elif miss:
                bad.append(f"원본이 요구하는 {len(want)}장 중 {len(miss)}장이 없습니다")
                todo.append("없는 이미지: " + ", ".join(sorted(miss)[:5])
                            + (" 외" if len(miss) > 5 else ""))
            else:
                ok.append(f"원본이 요구하는 {len(want)}장이 모두 있습니다")
        except Exception as e:
            bad.append(f"yaml 읽기 실패 — {e}")
            todo.append("yaml 파일의 들여쓰기가 깨졌을 수 있습니다")

    # 5. 결과 html
    for h in HERE.rglob("index.html"):
        text = h.read_text(encoding="utf-8", errors="ignore")
        imgs = text.count("<img")
        holes = text.count("아직 없음") + text.count('class="shot" data-src')
        if imgs:
            ok.append(f"{h.name} 에 이미지 {imgs}개가 붙어 있습니다")
        else:
            bad.append(f"{h.name} 에 이미지가 한 장도 안 붙었습니다 (빈자리 {holes}개)")
            todo.append("python build.py 를 다시 실행하세요")
        break

    # ---- 정리
    print("[ 진단 결과 ]\n")
    for tag, items in [("정상", ok), ("확인 필요", warn), ("문제", bad)]:
        if items:
            print(f"■ {tag}")
            for i in items:
                print(f"   - {i}")
            print()
    if todo:
        print("[ 해야 할 일 ]")
        for i, t in enumerate(todo, 1):
            print(f"   {i}. {t}")
        print()
    if not bad:
        print("큰 문제는 없습니다. python build.py 로 매뉴얼을 다시 만드세요.\n")
    print("이 출력을 그대로 복사해서 보내주시면 원인을 함께 볼 수 있습니다.")


if __name__ == "__main__":
    main()
