-- 도시 생존 네비게이터
-- 현재 샘플 flood_zones에서 동일 좌표·동일 점수로 반복 삽입된 행을 정리한다.
-- 애플리케이션의 점수 정규화 패치만으로도 과대 계산은 방지되며,
-- 이 SQL은 DB 초기 데이터 자체를 깔끔하게 정리하고 싶을 때 1회 실행한다.

begin;

-- 1. 삭제 전 원본을 별도 백업한다.
create table if not exists public.flood_zones_dedup_backup_20260618
as table public.flood_zones with no data;

insert into public.flood_zones_dedup_backup_20260618
select f.*
from public.flood_zones as f
where not exists (
    select 1
    from public.flood_zones_dedup_backup_20260618 as b
    where b.id = f.id
);

-- 2. 중심 좌표(소수점 5자리)와 base_score가 같은 행을 같은 샘플 구역으로 본다.
-- 이름이 가장 구체적인 행을 우선 보존하고 나머지 반복 행만 삭제한다.
with ranked as (
    select
        id,
        row_number() over (
            partition by
                round(center_lat::numeric, 5),
                round(center_lng::numeric, 5),
                base_score
            order by length(coalesce(zone_name, '')) desc, id asc
        ) as duplicate_rank
    from public.flood_zones
    where center_lat is not null
      and center_lng is not null
)
delete from public.flood_zones as f
using ranked as r
where f.id = r.id
  and r.duplicate_rank > 1;

notify pgrst, 'reload schema';

commit;

-- 실행 결과 확인
select
    id,
    zone_name,
    center_lat,
    center_lng,
    base_score
from public.flood_zones
order by center_lat, center_lng, id;
