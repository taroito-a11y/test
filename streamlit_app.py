import streamlit as st
from google import genai
import json
import urllib.parse

# ページ設定
st.set_page_config(page_title="店舗検索アプリ", page_icon="📍")
st.title("📍 AI店舗検索")

# 1. APIキーの読み込み（Secretsから取得）
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=API_KEY)
except Exception:
    st.error("APIキーが設定されていません。Streamlit Cloudの Settings > Secrets に 'GEMINI_API_KEY' を登録してください。")
    st.stop()

# 2. ユーザー入力
q = st.text_input("例：早稲田大学の近くのスーパー", placeholder="場所や店名を入力...")

if st.button("検索") and q:
    with st.spinner("AIが店舗を探しています..."):
        try:
            # 【重要】モデル名の指定を変更
            # ライブラリのバージョンにより 'gemini-1.5-flash' または 'models/gemini-1.5-flash' を試します
            # ここでは最新の推奨形式であるプレフィックスなしを試行
            response = client.models.generate_content(
                model="gemini-1.5-flash", 
                contents=f"""
                以下の文章から対象の地域を特定し、その周辺の店舗【5件のみ】厳選してJSONで出力してください。
                出力形式は必ず以下のキーを持つJSON配列にしてください。
                JSON以外の説明文は一切含めないでください。
                {{
                  "detected_location": "地域名",
                  "shops": [
                    {{"name": "店名", "reason": "おすすめ理由"}}
                  ]
                }}
                文章：{q}
                """
            )

            # JSONの解析
            res_text = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(res_text)
            
            location = data.get("detected_location", "不明な場所")
            st.success(f"「{location}」周辺の検索結果です。")

            # 3. 結果の表示
            for shop in data.get("shops", []):
                with st.expander(f"🏢 {shop['name']}"):
                    st.write(f"🌟 **理由:** {shop['reason']}")
                    
                    # Googleマップへのリンク
                    search_query = f"{shop['name']} {location}"
                    map_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(search_query)}"
                    
                    st.link_button("Googleマップを開く", map_url)

        except Exception as e:
            # 404エラーが続く場合のデバッグ用表示
            st.error(f"エラーが発生しました: {e}")
            if "404" in str(e):
                st.info("モデル名が見つからないようです。モデル名を 'gemini-2.0-flash-exp' に変更して試すか、ライブラリのバージョンを確認してください。")
