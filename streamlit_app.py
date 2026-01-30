import streamlit as st
import google.generativeai as genai
import requests
import math
import urllib.parse

st.set_page_config(page_title="店舗検索アプリ", page_icon="📍")
st.title("📍 実在店舗検索（Places連携 + AI要約）")

# ===== Keys =====
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
except Exception:
    st.error("Secretsに 'GEMINI_API_KEY' が設定されていません。")
    st.stop()

try:
    MAPS_API_KEY = st.secrets["GOOGLE_MAPS_API_KEY"]
except Exception:
    st.error("Secretsに 'GOOGLE_MAPS_API_KEY'（Google Maps PlatformのAPIキー）が設定されていません。")
    st.stop()

# ===== UI =====
q = st.text_input("検索地点・条件を入力", placeholder="例：早稲田大学の近くのスーパー")

col1, col2 = st.columns(2)
with col1:
    radius_label = st.radio("検索半径", ["500m", "1km", "2km"], horizontal=True)
with col2:
    priority = st.radio("重視するポイント", ["近さ重視", "評価重視"], horizontal=True)

radius_m = {"500m": 500, "1km": 1000, "2km": 2000}[radius_label]

st.caption("※ 店舗名・住所・評価はGoogle Placesの実データです。AIは要約・理由のみ生成します。")

# ===== Helpers =====
def geocode_address(text: str):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": text, "key": MAPS_API_KEY, "language": "ja"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK" or not data.get("results"):
        return None
    loc = data["results"][0]["geometry"]["location"]
    formatted = data["results"][0].get("formatted_address", text)
    return (loc["lat"], loc["lng"], formatted)

def places_nearby(lat: float, lng: float, radius: int, keyword: str):
    # Nearby Search: 実在店舗を半径で取得
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": radius,
        "keyword": keyword,
        "key": MAPS_API_KEY,
        "language": "ja",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        raise RuntimeError(f"Places API error: {data.get('status')} {data.get('error_message','')}")
    return data.get("results", [])

def place_details(place_id: str):
    # 住所を確実に取るためDetails
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,rating,user_ratings_total,url,geometry",
        "key": MAPS_API_KEY,
        "language": "ja",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK":
        raise RuntimeError(f"Place Details error: {data.get('status')} {data.get('error_message','')}")
    return data["result"]

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def ai_enrich(model, shops, user_query, center_label):
    # Geminiには「与えた店情報だけ」を使わせる（幻覚防止）
    # 口コミの実テキストはPlaces無料枠だと取りづらいので、ここでは「特徴要約」を生成
    # （必要なら別途、レビュー取得可能なAPI/スクレイピングは規約的に注意が必要）
    prompt = f"""
あなたは店舗選定アシスタントです。
次の「候補店舗リスト（実在データ）」以外の店舗名・住所は絶対に出力しないでください。
各店舗に対し「おすすめ理由」と「推定される口コミ傾向の短い要約（一般的な傾向）」を日本語で付けてください。
ユーザー要望: {user_query}
中心: {center_label}

出力はJSONのみ:
{{
  "shops": [
    {{
      "place_id": "...",
      "reason": "...",
      "reviews": "..."
    }}
  ]
}}

候補店舗リスト:
{[
    {
        "place_id": s["place_id"],
        "name": s["name"],
        "address": s["address"],
        "rating": s.get("rating"),
        "user_ratings_total": s.get("user_ratings_total"),
        "distance_m": s["distance_m"],
        "maps_url": s["maps_url"],
    } for s in shops
]}
"""
    resp = model.generate_content(prompt)
    text = resp.text.replace("```json", "").replace("```", "").strip()

    import json
    data = json.loads(text)
    by_id = {x["place_id"]: x for x in data.get("shops", [])}
    for s in shops:
        extra = by_id.get(s["place_id"], {})
        s["reason"] = extra.get("reason", "")
        s["reviews"] = extra.get("reviews", "")
    return shops

# ===== Main =====
if st.button("検索") and q:
    try:
        geo = geocode_address(q)
        if not geo:
            st.error("地点の特定に失敗しました。もう少し具体的に入力してください（例：駅名・施設名＋地域）。")
            st.stop()

        lat, lng, center_label = geo
        st.success(f"検索中心: {center_label}（半径 {radius_label}）")

        # Places: まず候補取得
        raw = places_nearby(lat, lng, radius_m, q)

        if not raw:
            st.warning("該当する店舗が見つかりませんでした。キーワードを変えて試してください。")
            st.stop()

        # Detailsで住所など確定
        shops = []
        for item in raw[:10]:  # 取りすぎ防止（課金＆速度対策）
            pid = item.get("place_id")
            if not pid:
                continue
            d = place_details(pid)
            gloc = d["geometry"]["location"]
            dist = haversine_m(lat, lng, gloc["lat"], gloc["lng"])
            shops.append({
                "place_id": pid,
                "name": d.get("name", ""),
                "address": d.get("formatted_address", ""),
                "rating": d.get("rating", None),
                "user_ratings_total": d.get("user_ratings_total", None),
                "maps_url": d.get("url", ""),
                "distance_m": int(dist),
            })

        # 並び替え
        if priority == "近さ重視":
            shops.sort(key=lambda x: x["distance_m"])
        else:
            # ratingがない店は後ろへ
            shops.sort(key=lambda x: (-(x["rating"] or -1), x["distance_m"]))

        # 上位5件
        shops = shops[:5]

        # Geminiで要約付与（幻覚対策：候補リスト限定）
        model = genai.GenerativeModel("models/gemini-2.0-flash")
        shops = ai_enrich(model, shops, q, center_label)

        # 表示
        for s in shops:
            rating = s["rating"]
            rating_text = f"{rating} / 5" if rating is not None else "評価なし"
            sub = f"⭐ {rating_text}・🧭 {s['distance_m']}m"

            with st.expander(f"🏢 {s['name']}（{sub}）"):
                st.write("📍 **住所**")
                st.write(s["address"])

                if s.get("user_ratings_total") is not None:
                    st.write("👥 **評価件数**")
                    st.write(str(s["user_ratings_total"]))

                if s.get("reviews"):
                    st.write("🗣️ **口コミ傾向（AI要約）**")
                    st.write(s["reviews"])

                if s.get("reason"):
                    st.write("✅ **おすすめ理由（AI）**")
                    st.write(s["reason"])

                if s.get("maps_url"):
                    st.link_button("Googleマップで開く", s["maps_url"])
                else:
                    # 保険：URLが無い場合は店名+住所で検索
                    query = f"{s['name']} {s['address']}".strip()
                    map_url = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(query)
                    st.link_button("Googleマップで検索", map_url)

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
