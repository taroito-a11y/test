import streamlit as st
from google import genai
from google.genai import types
import urllib.parse

st.title("店舗検索")

# 入力部分
q = st.text_input("例：早稲田大学の近くのスーパー", key="query")

if st.button("検索"):
    API_KEY = "AIzaSy..." # あなたのキー
    client = genai.Client(api_key=API_KEY)
    
    with st.spinner("検索中..."):
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"以下の文章から対象の地域を特定し、その周辺の店舗【5件のみ】厳選してJSONで出力してください。文章：{q}",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_maps=types.GoogleMaps())]
            )
        )
        
        # 結果を表示（JSONのまま出す場合）
        st.json(response.text)
        
        # 本来はここから先のループ処理で地図URLなどを作る
