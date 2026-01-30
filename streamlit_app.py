import streamlit as st
import google.generativeai as genai
import json
import urllib.parse

st.set_page_config(page_title="店舗検索アプリ", page_icon="📍")
st.title("📍 AI店舗検索（距離・重視軸切替対応）")

# 1. APIキー設定
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except Exception:
    st.error("APIキー設定エラー: Secretsに 'GEMINI_API_KEY' が設定されていません。")
    st.stop()

# 2. 入力
q = st.text_input(
    "検索地点・条件を入力",
    placeholder="例：早稲田大学の近くで静かなカフェ"
)

col1, col2 = st.columns(2)

with col1:
    radius = st.radio("検索半径", options=["500m", "1km", "2km"], horizontal=True)

with col2:
    priority = st.radio("重視するポイント", options=["近さ重視", "評価重視"], horizontal=True)

st.caption("※ 距離は徒歩圏内を目安にAIが判断します（厳密な測距ではありません）")
st.caption("※ 住所・評価・口コミ要約は参考情報です。正確な情報はGoogleマップ等でご確認ください。")

if st.button("検索") and q:
    with st.spinner("AIが店舗を診断中..."):
        try:
            target_model = "models/gemini-2.0-flash"
            model = genai.GenerativeModel(target_model)

            prompt = f"""
以下の文章から検索の中心となる地域を特定してください。

その地域の【中心地点から半径 {radius} 以内（徒歩圏内）】にある店舗のみを対象に、
条件に合う店舗を【5件のみ】厳選してください。

選定方針：
- 今回は「{priority}」で並び替え・選定してください
- 半径を超えると判断される店舗は含めないでください

必ず JSON 形式で出力してください。
マークダウンや説明文は不要です。

JSON形式：
{{
  "detected_location": "地域名",
  "shops": [
    {{
      "name": "店名",
      "address": "住所（可能な範囲で具体的に。番地やビル名まで分かれば含める）",
      "rating": 4.2,
      "reviews": "口コミの要約（良い点・悪い点を簡潔に）",
      "reason": "この店をおすすめする理由（距離や評価に言及）"
    }}
  ]
}}

※ rating は5点満点
※ reviews は一般的な口コミ傾向を要約したもの
※ address が不確かな場合は、最寄り駅や丁目レベルまでに留め、推測で番地を作らない

文章：
{q}
"""

            response = model.generate_content(prompt)

            text_data = (
                response.text
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

            data = json.loads(text_data)

            location = data.get("detected_location", "指定地点")
            st.success(f"「{location}」周辺（半径 {radius}・{priority}）の結果です")

            for shop in data.get("shops", []):
                name = shop.get("name", "")
                address = shop.get("address", "")
                rating = shop.get("rating", "")
                reviews = shop.get("reviews", "")
                reason = shop.get("reason", "")

                title = f"🏢 {name}"
                if rating != "":
                    title += f" ⭐ {rating} / 5"

                with st.expander(title):
                    if address:
                        st.write("📍 **住所**")
                        st.write(address)

                    if reviews:
                        st.write("🗣️ **口コミ要約**")
                        st.write(reviews)

                    if reason:
                        st.write("✅ **おすすめ理由**")
                        st.write(reason)

                    # Googleマップ検索は location を足さず、店名＋住所（あれば）で検索精度を上げる
                    query = name if not address else f"{name} {address}"
                    map_url = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(query)
                    st.link_button("Googleマップで見る", map_url)

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")

            if "404" in str(e) or "not found" in str(e):
                st.warning("⚠️ 利用可能なモデル一覧を表示します")
                try:
                    models = []
                    for m in genai.list_models():
                        if "generateContent" in m.supported_generation_methods:
                            models.append(m.name)
                    st.code("\n".join(models))
                except Exception as list_error:
                    st.error(f"モデル一覧の取得に失敗しました: {list_error}")
