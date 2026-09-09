# 아파트ok 매뉴얼 작업 폴더

이 폴더 하나로 매뉴얼 제작이 전부 돌아간다. 다른 폴더와 섞지 않는다.

## 폴더 구성

```
...\AptOK\메뉴얼\
  ├ build.py       원본 → 웹 매뉴얼 + FAQ + 툴팁 생성
  ├ capture.py     화면 촬영
  ├ verify.py      촬영본 검증 + 검토표 생성
  ├ doctor.py      폴더 상태 진단
  ├ routes.yaml    촬영 경로와 가림 설정
  ├ site.yaml      매뉴얼 제목
  ├ src\           원본 (여기만 고치면 된다)
  ├ captures\      촬영된 이미지 (자동 생성)
  ├ site\          완성된 웹 매뉴얼 (자동 생성)
  └ out\           FAQ, 툴팁 (자동 생성)
```

## 처음 한 번만

```powershell
pip install playwright pyyaml pillow
playwright install chromium
```

## 실행 순서

```powershell
cd "...\AptOK\메뉴얼"

$env:APTOK_ID="아이디"
$env:APTOK_PW="비밀번호"
$env:TEST_EMPLOYEE="직원이름"   # 개별 권한 설정 화면 촬영에 쓰임

python doctor.py            # 폴더 상태 확인
python capture.py --headed  # 화면 촬영 (창을 닫지 말 것)
python verify.py            # 검증 + review.html 생성
python build.py             # 매뉴얼 생성
```

결과는 `site\index.html`. 브라우저로 연다.

## 확인할 것

- `capture.py` 끝에 **"조회로 보이는데 차단된 요청"** 목록이 나오면, 화면에 자료가 비어 있을 수 있다. 그 이름 일부를 `routes.yaml`의 `allow_post`에 넣고 다시 촬영한다.
- `verify.py`가 만드는 `review.html`을 열어 설명과 화면이 맞는지, 가림이 적절한지 눈으로 확인한다.
- `build.py`가 **"붙임 N장 · 자리 비움 0장"**이라고 해야 이미지가 다 들어간 것이다.

## 주의

- 계정은 반드시 환경변수로 넘긴다. 명령줄에 직접 적으면 로그에 평문으로 남는다.
- 촬영이 끝날 때까지 브라우저 창을 닫지 않는다.
- 저장·삭제·발송 요청은 기본으로 차단된다. `--allow-write`는 테스트 계정에서만 쓴다.

## 현재 상태

| 항목 | 수치 |
|---|---|
| 전체 화면 | 63개 (2026-09-08 설문 관리 3개 추가) |
| 내용 작성 완료 | 4개 (권한관리 2, 공용업무 2) |
| 뼈대만 있는 화면 | 56개 |
| 공통 문서 | 1개 (목록 화면 공통 사용법) |
| 촬영 계획 | 64장 |
| 확인 필요 | 96건 |

**다음 할 일** — 64장 촬영. 하위 메뉴가 있는 화면(주차관리, 방송, 게시판관리, 관리비, 관리계획, 일일보고, 입주자대표회의, 선거관리위원회)은 클릭 경로가 제 짐작이라 실패할 수 있다. 실패 목록을 알려주면 경로를 고친다.
