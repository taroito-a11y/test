import streamlit as st
import google.generativeai as genai
import json
import urllib.parse

st.set_page_config(page_title="店舗検索アプリ", page_icon="📍")
st.title("📍 AI店舗検索（診断モード付き）")

# 1. APIキー設定
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except Exception:
    st.error("APIキー設定エラー: Secretsに 'GEMINI_API_KEY' が設定されていません。")
    st.stop()

# 2. 入力
q = st.text_input("例：早稲田大学の近くのスーパー", placeholder="検索したい場所を入力")

if st.button("検索") and q:
    with st.spinner("AIに接続中..."):
        try:
            # メインのモデル設定（まずはこれを試す）
            target_model = 'gemini-1.5-flash'
            model = genai.GenerativeModel(target_model)
            
            prompt = f"""
            以下の文章から対象の地域を特定し、その周辺の店舗【5件のみ】厳選してJSONで出力してください。
            JSON形式：{{"detected_location": "地域名", "shops": [{{"name": "店名", "reason": "理由"}}]}}
            余計なマークダウンは不要です。
            文章：{q}
            """
            
            response = model.generate_content(prompt)
            
            # 成功したら結果を表示
            text_data = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(text_data)
            
            location = data.get("detected_location", "場所")
            st.success(f"「{location}」周辺で見つかりました！")
            
            for shop in data.get("shops", []):
                with st.expander(f"🏢 {shop['name']}"):
                    st.write(shop['reason'])
                    url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(shop['name'] + ' ' + location)}"
                    st.link_button("Googleマップ", url)

        except Exception as e:
            # === エラー発生時の診断モード ===
            st.error(f"エラーが発生しました: {e}")
            
            if "404" in str(e) or "not found" in str(e):
                st.warning("⚠️ 指定したモデルが見つかりませんでした。現在あなたのAPIキーで利用可能なモデル一覧を取得します...")
                try:
                    # 利用可能なモデルをリストアップして表示
                    available_models = []
                    for m in genai.list_models():
                        if 'generateContent' in m.supported_generation_methods:
                            available_models.append(m.name)
                    
                    st.code("\n".join(available_models), language="text")
                    st.info("↑ 上記のリストにある名前（例: models/gemini-pro など）をコードの 'target_model' に設定すれば動きます。")
                except Exception as list_error:
                    st.error(f"モデル一覧の取得にも失敗しました: {list_error}")
