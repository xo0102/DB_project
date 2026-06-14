# 도시 생존 네비게이터 - 기능별 분할 버전

## 실행 방법

```bash
cd project_split_fixed
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# .streamlit/secrets.toml 안의 SUPABASE_URL, SUPABASE_KEY 수정
streamlit run app.py
```

## 구조

```text
project_split_fixed/
├── app.py
├── config.py
├── db/
├── services/
├── utils/
├── components/
├── views/
└── .streamlit/
```
