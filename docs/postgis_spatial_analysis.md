# 3단계: PostGIS 기반 경로 공간 분석

## 목표

기존 Python 중심점·반경 근사 방식에서 벗어나 다음 공간 연산을 PostgreSQL 내부에서 수행한다.

- TMAP 경로: `LineString`, SRID 4326
- 침수 구역: `MultiPolygon`, SRID 4326
- 사용자 신고 및 도로 알림: `geography(Point, 4326)`
- 침수 구역 판별: `ST_Intersects`
- 사용자 신고·도로 알림 판별: `ST_DWithin`

## 적용 파일

```text
sql/postgis_spatial_analysis.sql
services/spatial_service.py
services/route_risk_service.py
services/route_persistence_service.py
components/map_components.py
views/route_search.py
views/home.py
tests/test_spatial_service.py
```

## SQL 적용

Supabase Dashboard의 SQL Editor에서 `sql/postgis_spatial_analysis.sql` 전체를 실행한다.

SQL은 다음 작업을 수행한다.

1. PostGIS 확장 활성화
2. 공간 컬럼 추가
3. 기존 JSONB/위경도 데이터를 공간 컬럼으로 변환
4. 새 데이터가 들어올 때 자동 변환하는 트리거 생성
5. GiST 공간 인덱스 생성
6. `analyze_route_spatial` RPC 생성
7. `postgis_healthcheck` RPC 생성

## 추가되는 공간 컬럼

| 테이블 | 컬럼 | 자료형 | 용도 |
|---|---|---|---|
| `flood_zones` | `geom` | `geometry(MultiPolygon, 4326)` | 실제 침수 영역 |
| `route_results` | `route_geom` | `geometry(LineString, 4326)` | 저장된 TMAP 경로 |
| `report_risk_zones` | `geom` | `geography(Point, 4326)` | 신고 중심점 및 반경 계산 |
| `road_alerts` | `geom` | `geography(Point, 4326)` | 도로 알림 중심점 및 거리 계산 |

## 분석 방식

### 침수 Polygon이 있는 경우

```sql
ST_Intersects(route_line, flood_polygon)
```

실제로 교차하면 `ST_Intersection`과 `ST_Length`를 이용해 경로가 침수 영역 내부에 포함된 길이도 계산한다.

### 침수 Polygon이 없는 기존 행

기존 샘플 데이터 중 `geojson`이 비어 있거나 유효한 Polygon이 아닌 행은 중심점 기준 100m 보조 판별을 사용한다.

```sql
ST_DWithin(route_geography, flood_center_geography, 100)
```

화면에는 `중심점 반경 보조 판별`이라고 명확히 표시되므로 실제 Polygon 교차 결과와 구분할 수 있다.

### 사용자 신고 및 도로 알림

```sql
ST_DWithin(route_geography, risk_point_geography, radius_m)
```

사용자 신고는 각 행의 `radius_m`, 도로 알림은 기본 80m를 사용한다.

## 안전한 폴백

PostGIS RPC가 아직 설치되지 않았거나 오류가 발생하면 앱 전체를 중단하지 않고 기존 Python 거리 근사 방식으로 전환한다. 화면에는 폴백 사유가 경고로 표시된다.

## 확인 방법

홈 화면에서 다음 항목을 확인한다.

```text
PostGIS 버전
침수 Polygon 변환 개수
Polygon이 없어 보조 판별을 사용하는 침수 행 개수
저장된 경로 LineString 개수
신고·도로 알림 Point 개수
```

경로 검색 결과에서는 다음 내용을 확인한다.

```text
공간 분석 엔진: PostGIS
공간 판별: Polygon 실제 교차 / 신고 반경 ST_DWithin / 도로 알림 ST_DWithin
실제 교차 길이
지도 위 침수 Polygon
```

## 테스트

```bash
python -m unittest discover -s tests -v
```

Python 단위 테스트는 RPC 응답 파싱, GeoJSON 좌표 순서, PostGIS 결과와 날씨 점수 결합, 폴백 동작, 지도 Polygon 렌더링을 검사한다.
