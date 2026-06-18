# TMAP 지도 연동 2단계 패치 적용

기준 작업 폴더: `~/Desktop/project_split_fixed`

## 적용

```bash
cd ~/Desktop
rsync -av --exclude='.DS_Store' tmap_step2_map_patch/ project_split_fixed/
```

## 테스트 및 실행

```bash
cd ~/Desktop/project_split_fixed
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m streamlit run app.py
```

## 변경 파일

- `components/map_components.py`
- `views/route_search.py`
- `views/home.py`
- `config.py`
- `tests/test_route_map.py`

## 구현 내용

- 지도 클릭으로 출발지·도착지 선택
- 출발지를 선택하면 도착지 선택 모드로 자동 전환
- 출발·도착 바꾸기 및 초기화
- TMAP 경로를 Folium PolyLine으로 표시
- 출발지(초록)·도착지(빨강) 마커 표시
- 경로 전체가 보이도록 지도 범위 자동 조절
