# 도시 생존 네비게이터

Streamlit과 Supabase PostgreSQL을 이용한 웹 DB 응용 기본틀 프로젝트입니다.

이번 단계는 완성형 서비스가 아니라, 기존에 설계한 데이터베이스와 웹 화면을 연결하여 기본 UI 흐름과 DB 조회/입력 기능을 확인하는 것을 목표로 합니다.

## 1. 프로젝트 구조

```text
project/
├── app.py
├── requirements.txt
├── .gitignore
├── README.md
└── .streamlit/
    └── secrets.toml.example
```

실행할 때는 `.streamlit/secrets.toml.example` 파일을 복사해서 `.streamlit/secrets.toml` 파일을 직접 만들어야 합니다.

## 2. 포함된 기능

- 홈 화면
- 회원가입
- 로그인 / 로그아웃
- 위험 신고
- 위험 지도
- 간단 위험도 계산
- DB 테이블 조회
- 경로 검색 데모

## 3. 이번 단계에서 구현하지 않는 기능

- TMAP API 실제 연동
- 실제 도보 경로 탐색
- 경로별 위험도 비교
- 기상청 API 실시간 연동
- PostGIS 기반 공간 연산
- Polygon과 LineString의 실제 교차 판별

## 4. 설치 방법

바탕화면에 `project` 폴더를 만들었다고 가정합니다.

```bash
cd ~/Desktop/project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell을 사용하는 경우에는 다음처럼 가상환경을 실행할 수 있습니다.

```powershell
cd Desktop\project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 5. Supabase 연결 설정

`.streamlit` 폴더 안에 `secrets.toml` 파일을 새로 만듭니다.

```text
project/
└── .streamlit/
    ├── secrets.toml.example
    └── secrets.toml
```

`secrets.toml` 내용은 다음처럼 작성합니다.

```toml
SUPABASE_URL = "본인 Supabase URL"
SUPABASE_KEY = "본인 Supabase anon 또는 publishable key"
```

`secrets.toml` 파일은 `.gitignore`에 포함되어 있으므로 GitHub에 올리지 않습니다.

## 6. 실행 방법

```bash
streamlit run app.py
```

실행 후 브라우저에서 Streamlit 앱이 열리면 다음 순서로 테스트합니다.

1. 홈 화면에서 Supabase 연결 상태 확인
2. 회원가입 화면에서 테스트 사용자 생성
3. 로그인 화면에서 로그인
4. 위험 신고 화면에서 지도 클릭 후 신고 등록
5. 위험 지도 화면에서 신고 기반 위험 구역 확인
6. 간단 위험도 계산 화면에서 위치 클릭 후 위험도 확인
7. DB 테이블 조회 화면에서 주요 테이블 조회
8. 경로 검색 데모 화면 확인

## 7. 사용하는 Supabase 테이블

- `profiles`
- `flood_zones`
- `road_alerts`
- `weather_snapshots`
- `user_reports`
- `report_risk_zones`
- `route_search_logs`
- `route_results`
- `route_risk_details`

## 8. 주의사항

이 앱은 위 테이블이 Supabase에 이미 생성되어 있다는 전제로 동작합니다. 테이블명이나 컬럼명이 다르면 해당 부분을 DB 구조에 맞게 수정해야 합니다.
