-- 도시 생존 네비게이터 3단계
-- TMAP 경로 LineString과 침수 Polygon의 실제 교차 여부를 PostGIS로 분석한다.
-- Supabase Dashboard > SQL Editor에서 이 파일 전체를 한 번 실행한다.

-- Supabase의 일반적인 확장 스키마를 사용한다.
-- 이미 postgis가 gis 또는 public 스키마에 설치된 경우 CREATE EXTENSION은 그대로 유지된다.
create schema if not exists extensions;
create extension if not exists postgis with schema extensions;

set search_path = public, extensions, gis;

begin;

-- =========================================================
-- 1. GeoJSON 변환 유틸 함수
-- =========================================================

create or replace function public.geojson_to_geometry(p_geojson jsonb)
returns geometry
language plpgsql
immutable
set search_path = public, extensions, gis
as $$
declare
    v_type text;
    v_payload jsonb;
    v_geom geometry;
begin
    if p_geojson is null then
        return null;
    end if;

    v_type := upper(coalesce(p_geojson ->> 'type', ''));

    if v_type = 'FEATURE' then
        v_payload := p_geojson -> 'geometry';
    elsif v_type = 'FEATURECOLLECTION' then
        select ST_Collect(parsed.geom)
        into v_geom
        from (
            select public.geojson_to_geometry(feature.value) as geom
            from jsonb_array_elements(coalesce(p_geojson -> 'features', '[]'::jsonb)) as feature(value)
        ) as parsed
        where parsed.geom is not null;
    else
        v_payload := p_geojson;
    end if;

    if v_geom is null and v_payload is not null then
        v_geom := ST_GeomFromGeoJSON(v_payload::text);
    end if;

    if v_geom is null then
        return null;
    end if;

    if ST_SRID(v_geom) = 0 then
        v_geom := ST_SetSRID(v_geom, 4326);
    elsif ST_SRID(v_geom) <> 4326 then
        v_geom := ST_Transform(v_geom, 4326);
    end if;

    v_geom := ST_Force2D(v_geom);
    if not ST_IsValid(v_geom) then
        v_geom := ST_MakeValid(v_geom);
    end if;

    return v_geom;
exception
    when others then
        -- 기존 JSONB 중 일부가 GeoJSON이 아니어도 전체 마이그레이션이 중단되지 않게 한다.
        return null;
end;
$$;

create or replace function public.geojson_to_linestring(p_geojson jsonb)
returns geometry
language plpgsql
immutable
set search_path = public, extensions, gis
as $$
declare
    v_geom geometry;
    v_lines geometry;
begin
    v_geom := public.geojson_to_geometry(p_geojson);
    if v_geom is null then
        return null;
    end if;

    if GeometryType(v_geom) = 'LINESTRING' then
        return v_geom;
    end if;

    v_lines := ST_LineMerge(ST_CollectionExtract(v_geom, 2));
    if v_lines is null or ST_IsEmpty(v_lines) or GeometryType(v_lines) <> 'LINESTRING' then
        return null;
    end if;

    return ST_SetSRID(v_lines, 4326);
end;
$$;

create or replace function public.geojson_to_multipolygon(p_geojson jsonb)
returns geometry
language plpgsql
immutable
set search_path = public, extensions, gis
as $$
declare
    v_geom geometry;
    v_polygons geometry;
begin
    v_geom := public.geojson_to_geometry(p_geojson);
    if v_geom is null then
        return null;
    end if;

    v_polygons := ST_CollectionExtract(ST_MakeValid(v_geom), 3);
    if v_polygons is null or ST_IsEmpty(v_polygons) then
        return null;
    end if;

    return ST_SetSRID(ST_Multi(v_polygons), 4326);
end;
$$;

-- =========================================================
-- 2. 공간 컬럼 추가
-- =========================================================

alter table public.flood_zones
    add column if not exists geom geometry(MultiPolygon, 4326);

alter table public.route_results
    add column if not exists route_geom geometry(LineString, 4326);

alter table public.report_risk_zones
    add column if not exists geom geography(Point, 4326);

alter table public.road_alerts
    add column if not exists geom geography(Point, 4326);

-- =========================================================
-- 3. JSONB/좌표와 공간 컬럼 동기화 트리거
-- =========================================================

create or replace function public.sync_flood_zone_geom()
returns trigger
language plpgsql
set search_path = public, extensions, gis
as $$
begin
    new.geom := public.geojson_to_multipolygon(new.geojson);
    return new;
end;
$$;

drop trigger if exists trg_sync_flood_zone_geom on public.flood_zones;
create trigger trg_sync_flood_zone_geom
before insert or update of geojson
on public.flood_zones
for each row execute function public.sync_flood_zone_geom();

create or replace function public.sync_route_result_geom()
returns trigger
language plpgsql
set search_path = public, extensions, gis
as $$
begin
    new.route_geom := public.geojson_to_linestring(new.route_geojson);
    return new;
end;
$$;

drop trigger if exists trg_sync_route_result_geom on public.route_results;
create trigger trg_sync_route_result_geom
before insert or update of route_geojson
on public.route_results
for each row execute function public.sync_route_result_geom();

create or replace function public.sync_report_risk_zone_geom()
returns trigger
language plpgsql
set search_path = public, extensions, gis
as $$
begin
    if new.center_lat is null or new.center_lng is null
       or new.center_lat < -90 or new.center_lat > 90
       or new.center_lng < -180 or new.center_lng > 180 then
        new.geom := null;
    else
        new.geom := ST_SetSRID(ST_MakePoint(new.center_lng, new.center_lat), 4326)::geography;
    end if;
    return new;
end;
$$;

drop trigger if exists trg_sync_report_risk_zone_geom on public.report_risk_zones;
create trigger trg_sync_report_risk_zone_geom
before insert or update of center_lat, center_lng
on public.report_risk_zones
for each row execute function public.sync_report_risk_zone_geom();

create or replace function public.sync_road_alert_geom()
returns trigger
language plpgsql
set search_path = public, extensions, gis
as $$
begin
    if new.center_lat is null or new.center_lng is null
       or new.center_lat < -90 or new.center_lat > 90
       or new.center_lng < -180 or new.center_lng > 180 then
        new.geom := null;
    else
        new.geom := ST_SetSRID(ST_MakePoint(new.center_lng, new.center_lat), 4326)::geography;
    end if;
    return new;
end;
$$;

drop trigger if exists trg_sync_road_alert_geom on public.road_alerts;
create trigger trg_sync_road_alert_geom
before insert or update of center_lat, center_lng
on public.road_alerts
for each row execute function public.sync_road_alert_geom();

-- 기존 데이터도 공간 컬럼으로 변환한다.
update public.flood_zones
set geom = public.geojson_to_multipolygon(geojson)
where geojson is not null;

update public.route_results
set route_geom = public.geojson_to_linestring(route_geojson)
where route_geojson is not null;

update public.report_risk_zones
set geom = ST_SetSRID(ST_MakePoint(center_lng, center_lat), 4326)::geography
where center_lat between -90 and 90
  and center_lng between -180 and 180;

update public.road_alerts
set geom = ST_SetSRID(ST_MakePoint(center_lng, center_lat), 4326)::geography
where center_lat between -90 and 90
  and center_lng between -180 and 180;

-- =========================================================
-- 4. 공간 인덱스
-- =========================================================

create index if not exists flood_zones_geom_gix
    on public.flood_zones using gist (geom);

create index if not exists route_results_route_geom_gix
    on public.route_results using gist (route_geom);

create index if not exists report_risk_zones_geom_gix
    on public.report_risk_zones using gist (geom);

create index if not exists road_alerts_geom_gix
    on public.road_alerts using gist (geom);

-- =========================================================
-- 5. 경로 공간 위험 분석 RPC
-- =========================================================

create or replace function public.analyze_route_spatial(
    p_route_geojson jsonb,
    p_flood_fallback_radius_m integer default 100,
    p_road_alert_radius_m integer default 80
)
returns table (
    source_type text,
    source_id bigint,
    risk_type text,
    title text,
    risk_score integer,
    reason text,
    latitude double precision,
    longitude double precision,
    distance_to_route_m double precision,
    influence_radius_m integer,
    recent_report boolean,
    report_description text,
    report_created_at text,
    duplicate_count integer,
    route_position double precision,
    spatial_method text,
    overlap_length_m double precision,
    hazard_geojson jsonb
)
language plpgsql
stable
security invoker
set search_path = public, extensions, gis
as $$
declare
    v_route geometry(LineString, 4326);
begin
    v_route := public.geojson_to_linestring(p_route_geojson);

    if v_route is null or ST_IsEmpty(v_route) then
        raise exception 'p_route_geojson은 유효한 GeoJSON LineString이어야 합니다.'
            using errcode = '22023';
    end if;

    return query
    with route as (
        select v_route as geom, v_route::geography as geog
    ),
    flood_polygon_hits as (
        select
            'flood_zone'::text as source_type,
            f.id::bigint as source_id,
            'flood'::text as risk_type,
            coalesce(f.zone_name, '침수 위험 구역')::text as title,
            greatest(0, coalesce(f.base_score, 0))::integer as risk_score,
            format(
                'PostGIS ST_Intersects 결과, 경로 LineString이 침수 Polygon과 실제로 교차합니다. 겹친 길이 약 %sm.',
                round(spatial.overlap_m::numeric, 1)
            )::text as reason,
            coalesce(f.center_lat, ST_Y(ST_PointOnSurface(f.geom)))::double precision as latitude,
            coalesce(f.center_lng, ST_X(ST_PointOnSurface(f.geom)))::double precision as longitude,
            0::double precision as distance_to_route_m,
            0::integer as influence_radius_m,
            false as recent_report,
            ''::text as report_description,
            ''::text as report_created_at,
            0::integer as duplicate_count,
            ST_LineLocatePoint(r.geom, ST_ClosestPoint(r.geom, f.geom))::double precision as route_position,
            'polygon_intersection'::text as spatial_method,
            spatial.overlap_m::double precision as overlap_length_m,
            ST_AsGeoJSON(f.geom)::jsonb as hazard_geojson
        from public.flood_zones as f
        cross join route as r
        cross join lateral (
            select coalesce(
                ST_Length(
                    ST_CollectionExtract(ST_Intersection(r.geom, f.geom), 2)::geography
                ),
                0
            ) as overlap_m
        ) as spatial
        where f.geom is not null
          and ST_Intersects(r.geom, f.geom)
    ),
    flood_fallback_hits as (
        select
            'flood_zone'::text as source_type,
            f.id::bigint as source_id,
            'flood'::text as risk_type,
            coalesce(f.zone_name, '침수 위험 구역')::text as title,
            greatest(0, coalesce(f.base_score, 0))::integer as risk_score,
            format(
                '유효한 침수 Polygon이 없어 중심점 반경 %sm 보조 방식으로 판별했습니다. 경로와 최소 거리 약 %sm.',
                p_flood_fallback_radius_m,
                round(ST_Distance(r.geog, point_data.geog)::numeric, 1)
            )::text as reason,
            f.center_lat::double precision as latitude,
            f.center_lng::double precision as longitude,
            ST_Distance(r.geog, point_data.geog)::double precision as distance_to_route_m,
            p_flood_fallback_radius_m::integer as influence_radius_m,
            false as recent_report,
            ''::text as report_description,
            ''::text as report_created_at,
            0::integer as duplicate_count,
            ST_LineLocatePoint(
                r.geom,
                ST_ClosestPoint(r.geom, point_data.geom)
            )::double precision as route_position,
            'center_radius_fallback'::text as spatial_method,
            0::double precision as overlap_length_m,
            null::jsonb as hazard_geojson
        from public.flood_zones as f
        cross join route as r
        cross join lateral (
            select
                ST_SetSRID(ST_MakePoint(f.center_lng, f.center_lat), 4326) as geom,
                ST_SetSRID(ST_MakePoint(f.center_lng, f.center_lat), 4326)::geography as geog
        ) as point_data
        where f.geom is null
          and f.center_lat between -90 and 90
          and f.center_lng between -180 and 180
          and ST_DWithin(r.geog, point_data.geog, greatest(1, p_flood_fallback_radius_m))
    ),
    report_hits as (
        select
            'user_report'::text as source_type,
            coalesce(rz.report_id, ur.id)::bigint as source_id,
            coalesce(rz.risk_type, ur.risk_type, 'other')::text as risk_type,
            (
                '최근 사용자 신고 · ' ||
                case coalesce(rz.risk_type, ur.risk_type, 'other')
                    when 'flood' then '침수 위험'
                    when 'road_control' then '도로 통제'
                    else '기타 위험'
                end
            )::text as title,
            greatest(0, coalesce(rz.risk_score, 10))::integer as risk_score,
            format(
                'PostGIS ST_DWithin 결과, 신고 반경 %sm 안에 경로가 포함됩니다. 경로와 신고 지점의 최소 거리 약 %sm.',
                greatest(1, coalesce(rz.radius_m, 50)),
                round(ST_Distance(r.geog, rz.geom)::numeric, 1)
            )::text as reason,
            rz.center_lat::double precision as latitude,
            rz.center_lng::double precision as longitude,
            ST_Distance(r.geog, rz.geom)::double precision as distance_to_route_m,
            greatest(1, coalesce(rz.radius_m, 50))::integer as influence_radius_m,
            true as recent_report,
            coalesce(ur.description, '')::text as report_description,
            coalesce(ur.created_at, rz.created_at)::text as report_created_at,
            greatest(1, coalesce(ur.duplicate_count, 1))::integer as duplicate_count,
            ST_LineLocatePoint(
                r.geom,
                ST_ClosestPoint(r.geom, rz.geom::geometry)
            )::double precision as route_position,
            'report_radius'::text as spatial_method,
            0::double precision as overlap_length_m,
            null::jsonb as hazard_geojson
        from public.report_risk_zones as rz
        left join public.user_reports as ur on ur.id = rz.report_id
        cross join route as r
        where rz.active is true
          and (rz.expires_at is null or rz.expires_at >= now())
          and rz.geom is not null
          and ST_DWithin(r.geog, rz.geom, greatest(1, coalesce(rz.radius_m, 50)))
    ),
    road_hits as (
        select
            'road_alert'::text as source_type,
            a.id::bigint as source_id,
            coalesce(a.alert_type, 'road_control')::text as risk_type,
            coalesce(a.title, '도로 위험 알림')::text as title,
            greatest(0, coalesce(a.risk_score, 0))::integer as risk_score,
            format(
                'PostGIS ST_DWithin 결과, 활성 도로 알림이 경로에서 약 %sm 떨어져 있습니다. %s',
                round(ST_Distance(r.geog, a.geom)::numeric, 1),
                coalesce(a.description, '상세 설명 없음')
            )::text as reason,
            a.center_lat::double precision as latitude,
            a.center_lng::double precision as longitude,
            ST_Distance(r.geog, a.geom)::double precision as distance_to_route_m,
            p_road_alert_radius_m::integer as influence_radius_m,
            false as recent_report,
            ''::text as report_description,
            ''::text as report_created_at,
            0::integer as duplicate_count,
            ST_LineLocatePoint(
                r.geom,
                ST_ClosestPoint(r.geom, a.geom::geometry)
            )::double precision as route_position,
            'road_alert_radius'::text as spatial_method,
            0::double precision as overlap_length_m,
            null::jsonb as hazard_geojson
        from public.road_alerts as a
        cross join route as r
        where a.active is true
          and a.geom is not null
          and ST_DWithin(r.geog, a.geom, greatest(1, p_road_alert_radius_m))
    )
    select *
    from (
        select * from flood_polygon_hits
        union all
        select * from flood_fallback_hits
        union all
        select * from report_hits
        union all
        select * from road_hits
    ) as all_hits
    order by all_hits.route_position, all_hits.source_type, all_hits.source_id;
end;
$$;

revoke execute on function public.analyze_route_spatial(jsonb, integer, integer) from public;
grant execute on function public.analyze_route_spatial(jsonb, integer, integer) to anon, authenticated;

-- =========================================================
-- 6. 설치 상태 확인 RPC
-- =========================================================

create or replace function public.postgis_healthcheck()
returns jsonb
language sql
stable
security definer
set search_path = public, extensions, gis
as $$
    select jsonb_build_object(
        'enabled', true,
        'postgis_version', PostGIS_Version(),
        'flood_polygon_count', (
            select count(*) from public.flood_zones where geom is not null
        ),
        'flood_fallback_count', (
            select count(*) from public.flood_zones where geom is null
        ),
        'route_linestring_count', (
            select count(*) from public.route_results where route_geom is not null
        ),
        'report_point_count', (
            select count(*) from public.report_risk_zones where geom is not null
        ),
        'road_alert_point_count', (
            select count(*) from public.road_alerts where geom is not null
        )
    );
$$;

revoke execute on function public.postgis_healthcheck() from public;
grant execute on function public.postgis_healthcheck() to anon, authenticated;

notify pgrst, 'reload schema';

commit;

reset search_path;
