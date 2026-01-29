import streamlit as st
from google import genai
import json
import urllib.parse

# ページ設定
st.set_page_config(page_title="店舗検索アプリ", page_icon="📍")
st.title("📍 AI店舗検索")

# 1. APIキーの読み込み
try:
    # Streamlit Cloudの Secrets から取得
    API_KEY = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=API_KEY)
except Exception:
    st.error("APIキーが設定されていません。Secretsに 'GEMINI_API_KEY' を登録してください。")
    st.stop()

# 2. ユーザー入力
q = st.text_input("例：早稲田大学の近くのスーパー", placeholder="場所や店名を入力...")

if st.button("検索") and q:
    with st.spinner("AIが店舗を探しています..."):
        try:
            # モデル名は最も安定している 'gemini-1.5-flash' を使用
            # クォータエラーを避けるため、一旦Google Mapsツールを外してAIの知識で回答させます
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=f"""
                以下の文章から対象の地域を特定し、その周辺の店舗【5件のみ】厳選してJSONで出力してください。
                出力形式は必ず以下のキーを持つJSON配列にしてください。余計な文章は一切含めないでください。
                {{
                  "detected_location": "地域名",
                  "shops": [
                    {{"name": "店名", "reason": "おすすめ理由"}}
                  ]
                }}
                文章：{q}
                """
            )

            # JSONの整形（Markdownタグが含まれる場合を考慮）
            res_text = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(res_text)
            
            location = data.get("detected_location", "不明な場所")
            st.success(f"「{location}」周辺の検索結果です。")

            # 3. 結果の表示
            for shop in data.get("shops", []):
                with st.expander(f"🏢 {shop['name']}"):
                    st.write(f"🌟 **理由:** {shop['reason']}")
                    
                    # Googleマップへのリンクを生成
                    search_query = f"{shop['name']} {location}"
                    map_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(search_query)}"
                    
                    st.link_button("Googleマップを開く", map_url)

        except json.JSONDecodeError:
            st.error("AIからの回答を正しく解析できませんでした。もう一度お試しください。")
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            st.info("APIの制限にかかった可能性があります。1分ほど待ってから再度お試しください。")
