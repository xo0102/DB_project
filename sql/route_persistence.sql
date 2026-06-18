-- 도시 생존 네비게이터 2-2단계
-- 경로 검색 로그, 경로 결과, 경로별 위험 근거를 하나의 트랜잭션으로 저장한다.
-- Supabase Dashboard > SQL Editor에서 전체를 한 번 실행한다.

alter table public.route_search_logs enable row level security;
alter table public.route_results enable row level security;
alter table public.route_risk_details enable row level security;

grant select, insert, delete on table public.route_search_logs to authenticated;
grant select, insert, delete on table public.route_results to authenticated;
grant select, insert, delete on table public.route_risk_details to authenticated;

grant usage, select on sequence public.route_search_logs_id_seq to authenticated;
grant usage, select on sequence public.route_results_id_seq to authenticated;
grant usage, select on sequence public.route_risk_details_id_seq to authenticated;

-- 검색 로그: 로그인 사용자는 자신의 행만 저장·조회·삭제한다.
drop policy if exists "route_search_logs_insert_own" on public.route_search_logs;
create policy "route_search_logs_insert_own"
on public.route_search_logs
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists "route_search_logs_select_own" on public.route_search_logs;
create policy "route_search_logs_select_own"
on public.route_search_logs
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists "route_search_logs_delete_own" on public.route_search_logs;
create policy "route_search_logs_delete_own"
on public.route_search_logs
for delete
to authenticated
using (auth.uid() = user_id);

-- 경로 결과: 자신의 검색 로그에 연결된 행만 저장·조회·삭제한다.
drop policy if exists "route_results_insert_own" on public.route_results;
create policy "route_results_insert_own"
on public.route_results
for insert
to authenticated
with check (
    exists (
        select 1
        from public.route_search_logs as logs
        where logs.id = search_log_id
          and logs.user_id = auth.uid()
    )
);

drop policy if exists "route_results_select_own" on public.route_results;
create policy "route_results_select_own"
on public.route_results
for select
to authenticated
using (
    exists (
        select 1
        from public.route_search_logs as logs
        where logs.id = search_log_id
          and logs.user_id = auth.uid()
    )
);

drop policy if exists "route_results_delete_own" on public.route_results;
create policy "route_results_delete_own"
on public.route_results
for delete
to authenticated
using (
    exists (
        select 1
        from public.route_search_logs as logs
        where logs.id = search_log_id
          and logs.user_id = auth.uid()
    )
);

-- 위험 상세: 자신의 경로 결과에 연결된 행만 저장·조회·삭제한다.
drop policy if exists "route_risk_details_insert_own" on public.route_risk_details;
create policy "route_risk_details_insert_own"
on public.route_risk_details
for insert
to authenticated
with check (
    exists (
        select 1
        from public.route_results as results
        join public.route_search_logs as logs
          on logs.id = results.search_log_id
        where results.id = route_result_id
          and logs.user_id = auth.uid()
    )
);

drop policy if exists "route_risk_details_select_own" on public.route_risk_details;
create policy "route_risk_details_select_own"
on public.route_risk_details
for select
to authenticated
using (
    exists (
        select 1
        from public.route_results as results
        join public.route_search_logs as logs
          on logs.id = results.search_log_id
        where results.id = route_result_id
          and logs.user_id = auth.uid()
    )
);

drop policy if exists "route_risk_details_delete_own" on public.route_risk_details;
create policy "route_risk_details_delete_own"
on public.route_risk_details
for delete
to authenticated
using (
    exists (
        select 1
        from public.route_results as results
        join public.route_search_logs as logs
          on logs.id = results.search_log_id
        where results.id = route_result_id
          and logs.user_id = auth.uid()
    )
);

create or replace function public.save_route_recommendation(
    p_start_lat double precision,
    p_start_lng double precision,
    p_end_lat double precision,
    p_end_lng double precision,
    p_results jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_user_id uuid := auth.uid();
    v_search_log_id bigint;
    v_result jsonb;
    v_detail jsonb;
    v_route_result_id bigint;
    v_route_results jsonb := '[]'::jsonb;
    v_result_type text;
begin
    if v_user_id is null then
        raise exception '로그인 사용자만 경로 결과를 저장할 수 있습니다.'
            using errcode = '42501';
    end if;

    if p_start_lat not between -90 and 90
       or p_end_lat not between -90 and 90
       or p_start_lng not between -180 and 180
       or p_end_lng not between -180 and 180 then
        raise exception '출발지 또는 도착지 좌표 범위가 올바르지 않습니다.'
            using errcode = '22023';
    end if;

    if jsonb_typeof(p_results) is distinct from 'array' then
        raise exception '경로 결과는 JSON 배열 형식이어야 합니다.'
            using errcode = '22023';
    end if;

    if jsonb_array_length(p_results) = 0 then
        raise exception '저장할 경로 결과가 없습니다.'
            using errcode = '22023';
    end if;

    insert into public.route_search_logs (
        user_id,
        start_lat,
        start_lng,
        end_lat,
        end_lng,
        searched_at
    )
    values (
        v_user_id,
        p_start_lat,
        p_start_lng,
        p_end_lat,
        p_end_lng,
        now()
    )
    returning id into v_search_log_id;

    for v_result in
        select value
        from jsonb_array_elements(p_results)
    loop
        v_result_type := v_result ->> 'result_type';

        if v_result_type not in ('best', 'alternative_1', 'alternative_2') then
            raise exception '지원하지 않는 result_type: %', v_result_type
                using errcode = '22023';
        end if;

        insert into public.route_results (
            search_log_id,
            result_type,
            distance_m,
            duration_sec,
            total_risk_score,
            route_geojson,
            recommendation_reason,
            created_at
        )
        values (
            v_search_log_id,
            v_result_type,
            greatest(0, coalesce((v_result ->> 'distance_m')::integer, 0)),
            greatest(0, coalesce((v_result ->> 'duration_sec')::integer, 0)),
            least(100, greatest(0, coalesce((v_result ->> 'total_risk_score')::integer, 0))),
            coalesce(v_result -> 'route_geojson', '{}'::jsonb),
            coalesce(v_result ->> 'recommendation_reason', ''),
            now()
        )
        returning id into v_route_result_id;

        v_route_results := v_route_results || jsonb_build_array(
            jsonb_build_object(
                'id', v_route_result_id,
                'result_type', v_result_type
            )
        );

        if jsonb_typeof(v_result -> 'risk_details') = 'array' then
            for v_detail in
                select value
                from jsonb_array_elements(v_result -> 'risk_details')
            loop
                insert into public.route_risk_details (
                    route_result_id,
                    source_type,
                    source_id,
                    risk_type,
                    risk_score,
                    reason,
                    created_at
                )
                values (
                    v_route_result_id,
                    coalesce(v_detail ->> 'source_type', 'unknown'),
                    nullif(v_detail ->> 'source_id', '')::bigint,
                    coalesce(v_detail ->> 'risk_type', 'other'),
                    least(100, greatest(0, coalesce((v_detail ->> 'risk_score')::integer, 0))),
                    coalesce(v_detail ->> 'reason', ''),
                    now()
                );
            end loop;
        end if;
    end loop;

    return jsonb_build_object(
        'search_log_id', v_search_log_id,
        'route_results', v_route_results
    );
end;
$$;

revoke all on function public.save_route_recommendation(
    double precision,
    double precision,
    double precision,
    double precision,
    jsonb
) from public;

grant execute on function public.save_route_recommendation(
    double precision,
    double precision,
    double precision,
    double precision,
    jsonb
) to authenticated;

-- PostgREST가 새 함수를 즉시 인식하도록 스키마 캐시 갱신을 요청한다.
notify pgrst, 'reload schema';
