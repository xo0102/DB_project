# 도시 생존 네비게이터

## 현재 개발 단계

이번 버전은 **2-2단계: 경로 검색 결과와 위험 근거의 Supabase 저장**까지 구현한 버전입니다.

- 지도 클릭 기반 출발지·도착지 선택
- TMAP 보행자 경로 API 호출
- 기본 경로와 위험 회피 대안 경로 지도 표시
- 침수·도로 통제·최근 사용자 신고 기반 경로 위험 분석
- 위험도 50점 이상 또는 최근 신고 포함 시 대안 경로 탐색
- 로그인 사용자의 검색 결과 자동 저장
- 추천 경로를 `best`, 비교 경로를 `alternative_1`로 구분
- 경로 좌표를 표준 GeoJSON `LineString`으로 저장
- 경로별 위험 근거와 사용자 신고 내용을 별도 저장

다음 단계에서는 PostGIS를 도입하여 저장된 경로 `LineString`과 침수 구역 `Polygon`의 실제 교차 여부를 계산합니다.

## 실행 방법

```bash
cd ~/Desktop/project_split_fixed
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

`.streamlit/secrets.toml`에는 다음 값을 입력합니다.

```toml
SUPABASE_URL = "본인 Supabase URL"
SUPABASE_KEY = "본인 Supabase publishable 또는 anon key"
TMAP_APP_KEY = "본인 SK open API appKey"
```

실제 `secrets.toml`은 `.gitignore`에 포함되어 있으므로 GitHub에 업로드하지 않습니다.

## 최초 1회 Supabase 설정

Supabase Dashboard의 SQL Editor에서 아래 파일 내용을 실행합니다.

```text
sql/route_persistence.sql
```

이 SQL은 RLS 정책과 `save_route_recommendation` PostgreSQL 함수를 생성하여 세 테이블 저장을 하나의 트랜잭션으로 처리합니다.

- `route_search_logs`
- `route_results`
- `route_risk_details`

## 경로 검색 및 저장 흐름

```text
로그인
  ↓
지도에서 출발지·도착지 선택
  ↓
TMAP 기본 경로 조회
  ↓
위험 분석 및 필요 시 대안 경로 탐색
  ↓
route_search_logs 저장
  ↓
route_results 저장
  ↓
route_risk_details 저장
  ↓
지도와 경로 카드 출력
```

로그인하지 않은 상태에서도 경로 탐색은 가능하지만 DB 저장은 생략됩니다.

## 테이블별 저장 내용

### `route_search_logs`

- 사용자 ID
- 출발지/도착지 위도·경도
- 검색 시각

### `route_results`

- `best`: 위험 분석 결과 추천되는 경로
- `alternative_1`: 비교용 경로
- 거리와 예상 시간
- 전체 위험 점수
- GeoJSON LineString
- 추천 이유

### `route_risk_details`

- 위험 출처와 원본 데이터 ID
- 위험 유형과 점수
- 경로에 반영된 이유
- 사용자 신고 내용, 신고 시각, 누적 신고 수

## 테스트

```bash
python -m unittest discover -s tests -v
```

## 주요 구조

```text
project_split_fixed/
├── app.py
├── db/
│   └── queries.py
├── services/
│   ├── tmap_service.py
│   ├── route_risk_service.py
│   └── route_persistence_service.py
├── views/
│   └── route_search.py
├── sql/
│   └── route_persistence.sql
├── docs/
│   ├── risk_route_recommendation.md
│   └── route_result_persistence.md
└── tests/
    ├── test_tmap_service.py
    ├── test_route_map.py
    ├── test_route_risk_service.py
    └── test_route_persistence_service.py
```

## 다음 단계

- Supabase에서 PostGIS 확장 활성화
- `route_results.route_geojson`을 geometry `LineString`으로 변환
- `flood_zones.geojson`을 geometry `Polygon` 또는 `MultiPolygon`으로 변환
- `ST_Intersects`로 경로와 위험 구역의 실제 교차 여부 판별
- 공간 분석 결과로 `route_risk_details` 재계산
