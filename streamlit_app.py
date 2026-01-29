import streamlit as st
import google.generativeai as genai
import json
import urllib.parse

# ページ設定
st.set_page_config(page_title="店舗検索アプリ", page_icon="📍")
st.title("📍 AI店舗検索")

# 1. APIキーの設定
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    # 安定版ライブラリの設定方法
    genai.configure(api_key=API_KEY)
except Exception:
    st.error("APIキー設定エラー: Secretsに 'GEMINI_API_KEY' があるか確認してください。")
    st.stop()

# 2. ユーザー入力
q = st.text_input("例：早稲田大学の近くのスーパー", placeholder="場所や店名を入力...")

if st.button("検索") and q:
    with st.spinner("AIが店舗を探しています..."):
        try:
            # 【変更点】安定版のモデル定義
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # リクエスト送信
            prompt = f"""
            以下の文章から対象の地域を特定し、その周辺の店舗【5件のみ】厳選してJSONで出力してください。
            出力形式は必ず以下のキーを持つJSON配列にしてください。
            JSON以外の余計な文字（```json や ``` など）は一切含めず、純粋なJSONテキストのみを返してください。
            {{
              "detected_location": "地域名",
              "shops": [
                {{"name": "店名", "reason": "おすすめ理由"}}
              ]
            }}
            文章：{q}
            """
            
            response = model.generate_content(prompt)

            # テキストのクリーニング（念のため）
            res_text = response.text.replace("```json", "").replace("```", "").strip()
            
            # JSON変換
            data = json.loads(res_text)
            
            location = data.get("detected_location", "不明な場所")
            st.success(f"「{location}」周辺の検索結果です。")

            # 3. 結果の表示
            for shop in data.get("shops", []):
                with st.expander(f"🏢 {shop['name']}"):
                    st.write(f"🌟 **理由:** {shop['reason']}")
                    
                    # 地図リンク作成
                    search_query = f"{shop['name']} {location}"
                    map_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(search_query)}"
                    
                    st.link_button("Googleマップを開く", map_url)

        except json.JSONDecodeError:
            st.error("データの読み取りに失敗しました。もう一度検索ボタンを押してみてください。")
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            st.info("APIキーの権限や通信状況を確認してください。")
