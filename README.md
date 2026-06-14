# 도시 생존 네비게이터

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Web%20App-FF4B4B?logo=streamlit&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL%20%2B%20Auth-3ECF8E?logo=supabase&logoColor=white)
![Folium](https://img.shields.io/badge/Folium-Map-77B829)

> 침수 위험 구역, 도로 통제 정보, 날씨 정보, 사용자 신고 데이터를 기반으로  
> 비 오는 날 야간 도보 이동 시 참고할 수 있는 위험 정보를 제공하는 **Streamlit 기반 웹 DB 응용 기본틀**입니다.

---

## 1. 프로젝트 소개

**도시 생존 네비게이터**는 재난 상황, 특히 침수나 도로 통제처럼 이동 안전에 영향을 줄 수 있는 위험 정보를 웹 화면에서 조회하고 신고할 수 있도록 만든 프로젝트입니다.

이번 버전은 완성형 서비스라기보다, 데이터베이스와 웹 화면이 실제로 연결되는 흐름을 보여주는 **웹 DB 응용 기본틀**입니다. 기존에 하나의 파일에 모여 있던 코드를 기능별로 분리하여 유지보수성과 확장성을 높였습니다.

### 핵심 목표

- Supabase PostgreSQL과 Streamlit 웹 화면 연결
- Supabase Auth 기반 회원가입 / 로그인 / 로그아웃 구현
- 지도에서 위치를 선택하여 위험 신고 저장
- 신고 데이터를 기반으로 위험 구역 생성
- 침수 이력, 날씨, 신고 데이터를 활용한 간단 위험도 계산
- 주요 DB 테이블 조회 화면 제공
- 추후 TMAP API, 기상청 API, PostGIS 연동을 위한 기본 구조 마련

---

## 2. 주요 기능

| 기능 | 설명 |
|---|---|
| 홈 화면 | 프로젝트 개요, 현재 구현 기능, 추후 구현 예정 기능 표시 |
| 회원가입 | Supabase Auth에 사용자 계정 생성, `profiles` 테이블에 닉네임 저장 |
| 로그인 / 로그아웃 | Supabase Auth 기반 로그인 세션 관리 |
| 위험 신고 | 로그인 사용자가 지도에서 위치를 선택하고 위험 유형과 설명을 신고 |
| 중복 신고 병합 | 10분 이내, 30m 이내 동일 위험 유형 신고는 기존 신고와 병합 |
| 위험 지도 | 활성화된 신고 기반 위험 구역을 Folium 지도 위에 원 형태로 표시 |
| 간단 위험도 계산 | 선택 위치 기준으로 신고 구역, 침수 이력, 최신 날씨 점수를 합산 |
| DB 테이블 조회 | Supabase의 주요 테이블을 최대 100개 행까지 조회 |
| 경로 검색 데모 | 출발지 / 도착지 좌표 입력 UI와 추후 경로 탐색 흐름 제공 |

---

## 3. 기술 스택

| 구분 | 기술 |
|---|---|
| Language | Python |
| Web Framework | Streamlit |
| Database | Supabase PostgreSQL |
| Authentication | Supabase Auth |
| Map | Folium, streamlit-folium |
| Distance Calculation | geopy |
| Secret Management | `.streamlit/secrets.toml` |

---

## 4. 프로젝트 구조

```text
project/
├── app.py
├── config.py
├── requirements.txt
├── README.md
│
├── db/
│   ├── __init__.py
│   ├── client.py
│   └── queries.py
│
├── services/
│   ├── __init__.py
│   ├── auth_service.py
│   └── risk_service.py
│
├── views/
│   ├── __init__.py
│   ├── home.py
│   ├── auth.py
│   ├── risk_report.py
│   ├── risk_map.py
│   ├── risk_calculator.py
│   ├── db_viewer.py
│   └── route_demo.py
│
├── components/
│   ├── __init__.py
│   ├── sidebar.py
│   └── map_components.py
│
├── utils/
│   ├── __init__.py
│   ├── time_utils.py
│   ├── formatters.py
│   ├── geo_utils.py
│   └── state_utils.py
│
└── .streamlit/
    └── secrets.toml.example
```

---

## 5. 폴더별 역할

| 경로 | 역할 |
|---|---|
| `app.py` | Streamlit 앱의 진입점입니다. 메뉴 선택에 따라 각 화면을 호출합니다. |
| `config.py` | 앱 제목, 기본 좌표, 위험 유형, 메뉴 목록, DB 테이블 목록 등 공통 설정을 관리합니다. |
| `db/client.py` | Supabase 클라이언트 생성과 로그인 세션 복원을 담당합니다. |
| `db/queries.py` | DB 조회 함수를 모아둔 파일입니다. |
| `services/auth_service.py` | 회원가입, 로그인, 로그아웃, 프로필 생성 로직을 담당합니다. |
| `services/risk_service.py` | 위험 신고 저장, 중복 신고 병합, 위험 구역 생성, 위험도 계산 로직을 담당합니다. |
| `views/` | 사용자가 실제로 보는 화면 단위의 UI 코드를 관리합니다. |
| `components/` | 사이드바, 지도 컴포넌트처럼 여러 화면에서 재사용되는 UI 코드를 관리합니다. |
| `utils/` | 시간 처리, 좌표 처리, 자료형 변환, 세션 상태 관리 등 보조 함수를 관리합니다. |
| `.streamlit/` | Streamlit 실행에 필요한 비밀 설정 파일 예시를 보관합니다. |

---

## 6. 실행 방법

### 6-1. GitHub에서 클론한 경우

```bash
git clone https://github.com/xo0102/DB_project.git
cd DB_project
```

### 6-2. 기존 로컬 폴더에서 실행하는 경우

```bash
cd ~/Desktop/project_split_fixed
```

### 6-3. 가상환경 생성 및 활성화

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 6-4. 패키지 설치

```bash
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

### 6-5. Supabase 설정 파일 생성

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

그다음 `.streamlit/secrets.toml` 파일을 열고 본인의 Supabase 정보를 입력합니다.

```toml
SUPABASE_URL = "https://본인프로젝트.supabase.co"
SUPABASE_KEY = "본인 anon public key"
```

### 6-6. Streamlit 실행

```bash
streamlit run app.py
```

만약 `streamlit: command not found` 오류가 발생하면 아래 명령어로 실행합니다.

```bash
python3 -m streamlit run app.py
```

---

## 7. Supabase 설정 주의사항

실제 실행에 필요한 파일은 다음 파일입니다.

```text
.streamlit/secrets.toml
```

하지만 이 파일에는 Supabase URL과 API Key가 들어가므로 GitHub에 올리면 안 됩니다.

GitHub에는 예시 파일만 올립니다.

```text
.streamlit/secrets.toml.example
```

`.gitignore`에는 아래 내용이 포함되어 있어야 합니다.

```gitignore
.streamlit/secrets.toml
.venv/
__pycache__/
*.pyc
.DS_Store
```

---

## 8. 사용 DB 테이블

| 테이블명 | 용도 |
|---|---|
| `profiles` | 사용자 프로필 정보 저장 |
| `flood_zones` | 침수 이력 또는 침수 위험 구역 정보 저장 |
| `road_alerts` | 도로 통제 및 위험 알림 정보 저장 |
| `weather_snapshots` | 강수량, 예보 강수량, 날씨 위험 점수 저장 |
| `user_reports` | 사용자가 직접 신고한 위험 정보 저장 |
| `report_risk_zones` | 사용자 신고를 기반으로 생성된 활성 위험 구역 저장 |
| `route_search_logs` | 사용자의 경로 검색 요청 저장 예정 |
| `route_results` | 경로 후보별 거리, 시간, 위험 점수 저장 예정 |
| `route_risk_details` | 경로별 위험 근거 상세 정보 저장 예정 |

---

## 9. 주요 화면 구성

| 화면 | 파일 | 설명 |
|---|---|---|
| 홈 | `views/home.py` | 프로젝트 소개와 구현 기능 안내 |
| 로그인 / 회원가입 | `views/auth.py` | Supabase Auth 기반 인증 화면 |
| 위험 신고 | `views/risk_report.py` | 지도 클릭 기반 위험 신고 화면 |
| 위험 지도 | `views/risk_map.py` | 활성 위험 구역을 지도에 표시 |
| 간단 위험도 계산 | `views/risk_calculator.py` | 선택 위치 기준 위험도 점수 계산 |
| DB 테이블 조회 | `views/db_viewer.py` | Supabase 테이블 데이터 조회 |
| 경로 검색 데모 | `views/route_demo.py` | 출발지 / 도착지 좌표 입력 UI 제공 |

---

## 10. 기능 흐름

### 사용자 인증 흐름

```text
회원가입 화면
    ↓
Supabase Auth 사용자 생성
    ↓
profiles 테이블에 닉네임 저장
    ↓
로그인 화면에서 이메일 / 비밀번호 입력
    ↓
access_token, refresh_token을 session_state에 저장
    ↓
로그인 상태 유지
```

### 위험 신고 흐름

```text
로그인 사용자
    ↓
위험 신고 화면 접속
    ↓
지도에서 신고 위치 클릭
    ↓
위험 유형 선택 및 설명 입력
    ↓
1분 이내 동일 유형 신고 여부 확인
    ↓
10분 이내, 30m 이내 중복 신고 여부 확인
    ↓
신규 신고 저장 또는 기존 신고와 병합
    ↓
report_risk_zones 테이블에 반경 50m 위험 구역 생성 / 갱신
```

### 간단 위험도 계산 흐름

```text
지도에서 위치 선택
    ↓
신고 기반 위험 구역 포함 여부 확인
    ↓
침수 이력 구역과의 거리 확인
    ↓
최신 날씨 위험 점수 반영
    ↓
최종 위험도 점수 계산
```

---

## 11. 현재 구현 범위와 한계

이번 버전은 웹 DB 응용의 기본틀을 만드는 단계이므로 아래 기능은 아직 데모 또는 추후 구현 항목입니다.

- 실제 TMAP API 기반 도보 경로 탐색은 아직 연결하지 않았습니다.
- 기상청 API 실시간 연동은 아직 구현하지 않았습니다.
- PostGIS 기반 Polygon 교차 판별은 아직 구현하지 않았습니다.
- 현재 위험도 계산은 거리 기반 단순 합산 방식입니다.
- 실제 서비스 수준의 보안 정책, 예외 처리, 배포 설정은 추가 개선이 필요합니다.

---

## 12. 향후 개선 계획

- TMAP API를 활용한 실제 도보 경로 후보 생성
- 경로별 침수 위험도 비교 기능 구현
- 기상청 API를 통한 실시간 강수량 / 예보 데이터 반영
- 도로 통제 데이터 자동 수집 및 갱신
- PostGIS를 활용한 공간 데이터 처리 고도화
- 경로 LineString과 침수 Polygon의 교차 여부 판별
- 관리자용 위험 신고 검토 화면 추가
- 신고 신뢰도 및 사용자 평판 점수 반영

---

## 13. 자주 발생하는 오류

### `KeyError: SUPABASE_URL`

`.streamlit/secrets.toml` 파일이 없거나 값이 입력되지 않은 경우입니다.

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

이후 `SUPABASE_URL`, `SUPABASE_KEY` 값을 입력해야 합니다.

### `ModuleNotFoundError`

프로젝트 최상위 폴더가 아닌 곳에서 실행했을 가능성이 높습니다.

항상 `app.py`가 있는 폴더에서 실행합니다.

```bash
streamlit run app.py
```

### `relation does not exist`

Supabase에 해당 테이블이 없거나 테이블명이 코드와 다른 경우입니다.

`config.py`의 `DB_TABLES` 목록과 Supabase 실제 테이블 이름을 비교해야 합니다.

### 로그인은 되지만 신고가 안 되는 경우

Supabase의 RLS 정책 또는 테이블 권한 문제일 수 있습니다. 특히 아래 테이블에 대해 insert / select / update 권한을 확인해야 합니다.

```text
profiles
user_reports
report_risk_zones
```

---

## 14. 리팩토링 목적

기존에는 하나의 파일에 설정, DB 연결, 인증, 위험 신고, 지도, 화면 렌더링 코드가 함께 들어있었습니다. 이번 리팩토링에서는 기능별로 파일을 분리하여 다음과 같은 장점을 얻었습니다.

- 화면 코드와 비즈니스 로직 분리
- Supabase 연결 코드 재사용 가능
- 인증 로직과 위험도 계산 로직 분리
- 파일별 책임이 명확해져 유지보수 용이
- 추후 API 연동, 관리자 기능, 경로 추천 기능 확장에 유리

---

## 15. 프로젝트 상태

현재 프로젝트는 **웹 DB 응용 기본틀 구현 단계**입니다.  
데이터베이스 연결, 인증, 신고 저장, 지도 표시, 테이블 조회 등 핵심 흐름을 확인할 수 있으며, 이후 실제 API와 공간 데이터베이스 기능을 연결하여 고도화할 수 있습니다.