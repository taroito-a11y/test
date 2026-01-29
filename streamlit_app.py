import streamlit as st
from google import genai
from google.genai import types
import urllib.parse
import json

st.title("📍 店舗検索アプリ")

# 1. APIキーをSecretsから取得（直書きを廃止）
# 注意: ここで "GEMINI_API_KEY" という名前で呼び出しているので、
# Streamlit CloudのSecrets設定画面でも同じ名前で保存してください。
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("APIキーが設定されていません。Streamlit CloudのSettings > Secrets に 'GEMINI_API_KEY' を登録してください。")
    st.stop()

# クライアントの初期化
client = genai.Client(api_key=API_KEY)

# 2. ユーザー入力
q = st.text_input("例：早稲田大学の近くのスーパー", key="query")

if st.button("検索") and q:
    with st.spinner("Geminiが検索中..."):
        try:
            # Geminiにリクエスト
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"""
                以下の文章から対象の地域を特定し、その周辺の店舗【5件のみ】厳選してJSONで出力してください。
                出力形式は必ず以下のキーを持つJSONにしてください。
                {{
                  "detected_location": "地域名",
                  "shops": [
                    {{"name": "店名", "reason": "おすすめ理由"}}
                  ]
                }}
                文章：{q}
                """,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_maps=types.GoogleMaps())]
                )
            )

            # JSONテキストの抽出（Markdownの装飾を消す）
            res_text = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(res_text)
            
            location = data.get("detected_location", "不明な場所")
            st.success(f"「{location}」周辺の検索結果です。")

            # 3. 結果の表示と地図URLの生成
            for shop in data.get("shops", []):
                with st.expander(f"🏢 {shop['name']}"):
                    st.write(f"🌟 **理由:** {shop['reason']}")
                    
                    # 地図URLの生成（検索クエリを作成）
                    search_query = f"{shop['name']} {location}"
                    map_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(search_query)}"
                    
                    st.link_button("Googleマップで見る", map_url)

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            st.info("APIキーが正しいか、Google AI Studioで Gemini 2.0 Flash が使えるか確認してください。")
