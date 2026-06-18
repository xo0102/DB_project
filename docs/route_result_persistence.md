# 2-2단계: 경로 검색 결과 DB 저장

## 저장 흐름

```text
지도에서 출발지·도착지 선택
        ↓
TMAP 기본/대안 경로 검색
        ↓
위험도 및 최근 신고 분석
        ↓
route_search_logs 1건 저장
        ↓
route_results 1~2건 저장
        ↓
route_risk_details N건 저장
```

## 테이블별 저장 내용

### `route_search_logs`

- 로그인 사용자 ID
- 출발지 위도·경도
- 도착지 위도·경도
- 검색 시각

### `route_results`

- `best`: 현재 분석에서 추천되는 경로
- `alternative_1`: 비교용 기본 또는 우회 경로
- 거리, 예상 시간, 전체 위험 점수
- 표준 GeoJSON `LineString`
- 추천 이유

위험 회피 경로가 기본 경로보다 안전하면 위험 회피 경로를 `best`로 저장한다.

### `route_risk_details`

- 사용자 신고, 침수 이력, 도로 통제, 날씨 등 위험 출처
- 위험 데이터 ID
- 위험 유형과 점수
- 경로에 반영된 구체적인 이유
- 사용자 신고인 경우 신고 내용·시간·누적 신고 수

## RLS 설정

Supabase SQL Editor에서 `sql/route_persistence.sql`을 한 번 실행해야 한다.
로그인하지 않은 사용자는 경로 탐색과 화면 확인은 가능하지만 검색 결과는 DB에 저장하지 않는다.

## 트랜잭션 처리

`save_route_recommendation` PostgreSQL 함수를 RPC로 호출하여 세 테이블 저장을 하나의 트랜잭션으로 처리한다. 중간 단계에서 오류가 발생하면 해당 검색 묶음 전체가 롤백된다.
