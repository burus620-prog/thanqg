#!/usr/bin/env python3
"""아파트ok 전체 화면의 원본 뼈대와 캡처 경로를 생성한다.

메뉴 구조에서 확실히 알 수 있는 것만 채우고, 화면을 봐야 아는 것은
'확인필요'로 남긴다. 캡처가 모이면 그 위에 내용을 얹는다.
"""
import pathlib

OUT = pathlib.Path("/home/claude/manual")

# (id, 이름, 상단메뉴, 좌측메뉴, 하위메뉴, 패턴, 목적, 표시)
# 목적이 None 이면 화면을 봐야 알 수 있는 것 → 확인필요로 남긴다
# 표시: pii=개인정보, danger=되돌릴 수 없는 동작, legal=법정 마감
S = [
 # 관리업무
 ("mgmt-household-work","세대업무","관리업무","세대업무",None,"A","특정 세대에서 발생한 업무를 접수하고 처리 결과를 남긴다",""),
 ("mgmt-complaint-eval","민원평가현황","관리업무","민원평가현황",None,"D",None,""),
 ("mgmt-photos","사진함","관리업무","사진함",None,"A","업무 사진을 모아 보관하고 찾아본다",""),
 ("mgmt-doc-office","문서수불(관리사무소)","관리업무","문서수불(관리사무소)",None,"A","관리사무소가 주고받은 문서를 기록한다",""),
 ("mgmt-doc-council","문서수불(입주자대표회의)","관리업무","문서수불(입주자대표회의)",None,"A","입주자대표회의가 주고받은 문서를 기록한다",""),
 ("mgmt-doc-election","문서수불(선거관리위원회)","관리업무","문서수불(선거관리위원회)",None,"A","선거관리위원회가 주고받은 문서를 기록한다",""),
 ("mgmt-notice","공고문","관리업무","공고문",None,"A","단지에 게시할 공고문을 작성하고 관리한다",""),
 ("mgmt-materials","각종자료","관리업무","각종자료",None,"A","업무에 쓰는 자료를 보관한다",""),
 ("mgmt-parking-vehicle","차량관리","관리업무","주차관리","차량관리","A","단지에 등록된 차량을 관리한다",""),
 ("mgmt-parking-enforce","주차단속","관리업무","주차관리","주차단속","A","주차 위반 단속 내역을 기록한다",""),
 ("mgmt-broadcast-notice","안내방송","관리업무","방송","안내방송","B",None,"danger"),
 ("mgmt-broadcast-done","완료방송","관리업무","방송","완료방송","B",None,"danger"),
 ("mgmt-board-sample","샘플 서식/양식","관리업무","게시판관리","샘플 서식/양식","E","기본 제공되는 서식과 양식을 본다",""),
 ("mgmt-board-complex","단지 서식/양식","관리업무","게시판관리","단지 서식/양식","E","단지에서 직접 쓰는 서식과 양식을 관리한다",""),
 ("mgmt-fee-stats","관리비 통계","관리업무","관리비","관리비 통계","D","관리비를 항목별·기간별로 집계해 본다",""),
 ("mgmt-fee-household","세대 관리비","관리업무","관리비","세대 관리비","D","세대별 관리비를 조회한다","pii"),
 ("mgmt-security","보안","관리업무","보안",None,"D","개인정보 관련 문서를 내려받은 계정의 기록을 조회한다",""),
 # 법정일정
 ("legal-monthly","월간일정","법정일정","월간일정",None,"D","그 달에 해야 할 법정 업무를 한눈에 본다","legal"),
 ("legal-personal","개인일정","법정일정","개인일정",None,"A","담당자 본인의 일정을 관리한다",""),
 ("legal-safety","안전점검","법정일정","관리계획","안전점검","C",None,"legal"),
 ("legal-inspection","법정검사","법정일정","관리계획","법정검사","C",None,"legal"),
 ("legal-report","등록/신고/보고","법정일정","관리계획","등록/신고/보고","C",None,"legal"),
 ("legal-disclosure","공개/게시/청취","법정일정","관리계획","공개/게시/청취","C",None,"legal"),
 ("legal-edu-ext","외부교육","법정일정","관리계획","외부교육","C",None,"legal"),
 ("legal-edu-int","자체교육","법정일정","관리계획","자체교육","C",None,"legal"),
 # 전자결재
 ("appr-draft","기안품의","전자결재","기안품의",None,"B",None,"danger"),
 ("appr-report","업무보고","전자결재","업무보고",None,"B",None,"danger"),
 ("appr-order","지시사항","전자결재","지시사항",None,"A","지시받은 사항을 기록하고 처리 상태를 관리한다",""),
 ("appr-log-power","수변전일지","전자결재","일일보고","수변전일지","C","수변전 설비 운전 상황을 매일 기록한다",""),
 ("appr-log-generator","발전기 운전일지","전자결재","일일보고","발전기 운전일지","C","발전기 운전 상황을 기록한다",""),
 ("appr-log-heating","난방일지","전자결재","일일보고","난방일지","C","난방 설비 운전 상황을 기록한다",""),
 ("appr-log-fire","소방일지","전자결재","일일보고","소방일지","C","소방 설비 점검 상황을 기록한다",""),
 ("appr-log-security","경비일지","전자결재","일일보고","경비일지","C","경비 근무 상황을 기록한다",""),
 ("appr-log-daily","일일일지","전자결재","일일보고","일일일지","C",None,""),
 ("appr-guard","경비","전자결재","경비",None,"C",None,""),
 ("appr-cleaning","미화","전자결재","미화",None,"C",None,""),
 ("appr-facility","주민공동시설","전자결재","주민공동시설",None,"A",None,""),
 # 자산관리
 ("asset-stock-private","저장품(전용)","자산관리","저장품(전용)",None,"A",None,""),
 ("asset-stock-common","저장품(공용)","자산관리","저장품(공용)",None,"A",None,""),
 ("asset-tools","공기구","자산관리","공기구",None,"A","관리사무소가 보유한 공구와 기구를 관리한다",""),
 ("asset-furniture","집기비품","자산관리","집기비품",None,"A","사무용 집기와 비품을 관리한다",""),
 # 입주자관리
 ("res-household","세대관리","입주자관리","세대관리",None,"A","세대별 입주자 정보를 관리한다","pii"),
 ("res-arrears","체납세대","입주자관리","체납세대",None,"D","관리비를 내지 않은 세대를 조회한다","pii"),
 ("res-council-list","입주자대표회의 명단","입주자관리","입주자대표회의","명단","E","입주자대표회의 구성원 명단을 관리한다","pii"),
 ("res-council-minutes","입주자대표회의 회의록","입주자관리","입주자대표회의","회의록","A","회의록을 작성하고 보관한다",""),
 ("res-election-list","선거관리위원회 명단","입주자관리","선거관리위원회","명단","E","선거관리위원회 구성원 명단을 관리한다","pii"),
 ("res-election-minutes","선거관리위원회 회의록","입주자관리","선거관리위원회","회의록","A","회의록을 작성하고 보관한다",""),
 ("res-community","공동체","입주자관리","공동체",None,"A",None,""),
 # 인사관리
 ("hr-staff","직원현황","인사관리","직원현황",None,"A","직원을 등록하고 직책과 권한 방식을 지정한다","pii"),
 ("hr-rank","직급부서","인사관리","직급부서",None,"E","단지에서 쓰는 직급과 부서를 정한다",""),
 ("hr-duty","업무분장","인사관리","업무분장",None,"E",None,""),
 ("hr-leave","휴가관리","인사관리","휴가관리",None,"A","직원 휴가를 신청하고 관리한다","pii"),
 ("hr-edu-ext","외부교육","인사관리","외부교육",None,"A","직원이 받은 외부 교육 이력을 기록한다",""),
 ("hr-edu-int","자체교육","인사관리","자체교육",None,"A","단지 자체 교육 실시 내역을 기록한다",""),
 ("hr-appointment","법정선임","인사관리","법정선임",None,"C",None,"legal"),
 # 입찰계약
 ("bid-contract","계약현황","입찰계약","계약현황",None,"A","단지가 맺은 계약을 관리한다",""),
]

GROUPS = {
 "관리업무": "mgmt-work", "법정일정": "legal-schedule", "전자결재": "approval",
 "자산관리": "asset", "입주자관리": "resident", "인사관리": "hr", "입찰계약": "bid",
}

PERM = {"관리업무":"관리업무","법정일정":"법정일정","전자결재":"전자결재",
        "자산관리":"자산관리","입주자관리":"입주자관리","인사관리":"인사관리",
        "입찰계약":"입찰계약"}


def screen_yaml(s):
    sid, name, top, side, sub, pat, purpose, flag = s
    path = f"{top} > {side}" + (f" > {sub}" if sub else "")
    nav = f"상단 [{top}]를 클릭한 뒤 왼쪽 목록에서 [{side}]"
    nav += f"를 클릭하고 [{sub}]를 클릭합니다." if sub else "를 클릭합니다."
    target = f"nav:{top} > side:{side}" + (f" > side:{sub}" if sub else "")

    L = [f"- screen_id: {sid}",
         f"  screen_name: {name}",
         f"  path: {path}",
         f"  pattern: {pat}"]
    if pat == "A":
        L.append("  inherits: pattern-a")
    L.append(f"  permission: {PERM[top]} > 열람")
    L.append("  draft: true                     # 화면 확인 전 뼈대")
    if purpose:
        L.append(f"  purpose: {purpose}")
    else:
        L.append("  purpose: null                   # 확인필요: 이 화면이 무엇을 하는 화면인지")
    if flag == "legal":
        L += ["  legal_basis: null               # 확인필요: 근거 조문",
              "  deadline: null                  # 확인필요: 마감일"]
    L += ["", "  steps:", "    - no: 1",
          f"      action: {nav}",
          f"      target: {target}",
          f"      image: {sid}-01.png",
          "      note: null"]
    if pat == "A":
        L += ["    - no: 2",
              "      action: 검색·기간·내려받기 등 기본 조작은 [목록 화면 공통 사용법]을 따릅니다.",
              "      target: null", "      image: null", "      note: null"]
    L.append("")
    L.append("  cautions:")
    if flag == "pii":
        L.append('    - "개인정보가 표시되는 화면입니다. 열람 권한을 꼭 필요한 직원에게만 주세요."')
    if flag == "danger":
        L.append('    - "실제로 실행되는 동작입니다. 연습 삼아 누르지 마세요."   # 확인필요: 정확한 동작 범위')
    if flag not in ("pii", "danger"):
        L.append("    []   # 확인필요: 되돌릴 수 없는 동작이 있는지")
    L += ["", "  faq: []", ""]
    if flag == "pii":
        L += ["  privacy_note: 캡처 시 이름·동호수·연락처를 가린다.", ""]
    return "\n".join(L)


def route_yaml(s):
    sid, name, top, side, sub, pat, purpose, flag = s
    L = [f"  - screen_id: {sid}"]
    if flag == "pii":
        L.append("    mask: []   # 확인필요: 개인정보 영역 CSS 선택자")
    L += ["    steps:", f"      - top: {top}", f"      - side: {side}"]
    if sub:
        L.append(f"      - side: {sub}")
    L += ["      - wait: 900", f"      - shot: {sid}-01.png"]
    return "\n".join(L)


# 대분류별로 파일을 나눈다
by_group = {}
for s in S:
    by_group.setdefault(GROUPS[s[2]], []).append(s)

for fname, items in by_group.items():
    head = (f"# 아파트ok 사용자 매뉴얼 원본 — {items[0][2]}\n"
            f"# 화면 {len(items)}개. draft: true 인 항목은 화면 확인 전 뼈대이며,\n"
            f"# 캡처를 본 뒤 purpose·steps·cautions·faq 를 채운다.\n\n")
    (OUT / "src" / f"{fname}.yaml").write_text(
        head + "\n---\n\n".join(screen_yaml(s) for s in items) + "\n", encoding="utf-8")
    print(f"src/{fname}.yaml — {len(items)}개 화면")

routes = ["", "  # ── 아래는 전체 화면 뼈대. 화면당 1장씩 촬영한다.",
          "  # expect 는 화면을 본 뒤 채운다. 그 전까지는 중복 감지로 이동 실패를 잡는다.", ""]
routes += [route_yaml(s) + "\n" for s in S]
(OUT / "capture" / "routes.append.yaml").write_text("\n".join(routes), encoding="utf-8")
print(f"capture/routes.append.yaml — {len(S)}개 경로")
