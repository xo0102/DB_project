# TMAP 1단계 패치 적용

이 폴더의 내용을 기존 Git 저장소 최상위 폴더에 복사합니다.

복사 후 기존 데모 화면 파일을 삭제합니다.

```bash
rm -f views/route_demo.py
```

실제 `.streamlit/secrets.toml`에는 다음 줄을 직접 추가합니다.

```toml
TMAP_APP_KEY = "본인 SK open API appKey"
```

패키지 설치와 테스트:

```bash
pip install -r requirements.txt
python3 -m unittest discover -s tests -v
streamlit run app.py
```
