import math
import json
import urllib.parse

import requests
import streamlit as st
import google.generativeai as genai


st.set_page_config(page_title="店舗検索アプリ", page_icon="📍")
st.title("📍 実在店舗検索（Places連携 + AI要約）")


# =========================
# Secrets / API Keys
# =========================
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


# =========================
# UI
# =========================
center = st.text_input(
    "検索中心（地名・駅名・施設名）",
    placeholder="例：早稲田大学 / 新宿駅 / 東京駅"
)

keyword = st.text_input(
    "探したいお店（キーワード）",
    placeholder="例：スーパー / カフェ 静か / ラーメン"
)

col1, col2 = st.columns(2)
with col1:
    radius_label = st.radio("検索半径", ["500m", "1km", "2km"], horizontal=True)
with col2:
    priority = st.radio("重視するポイント", ["近さ重視", "評価重視"], horizontal=True)

radius_m = {"500m": 500, "1km": 1000, "2km": 2000}[radius_label]

st.caption("※ 店舗名・住所・評価・距離はGoogle Placesの実データです。AIは要約・理由のみ生成します。")
st.caption("※ 口コミ本文の取得・表示は行いません（規約・フィールド制限に配慮し、傾向のみAIで要約します）。")


# =========================
# Helpers (Google APIs)
# =========================
def geocode_address(text: str):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": text,
        "key": MAPS_API_KEY,
        "language": "ja",
        "region": "jp",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    status = data.get("status")
    if status != "OK" or not data.get("results"):
        st.error(f"地点の特定に失敗しました（Geocoding）。status={status} / message={data.get('error_message','')}")
        st.code(data, language="json")
        return None

    loc = data["results"][0]["geometry"]["location"]
    formatted = data["results"][0].get("formatted_address", text)
    return (loc["lat"], loc["lng"], formatted)


def places_nearby(lat: float, lng: float, radius: int, keyword_text: str):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": radius,
        "keyword": keyword_text,
        "key": MAPS_API_KEY,
        "language": "ja",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    status = data.get("status")
    if status not in ("OK", "ZERO_RESULTS"):
        raise RuntimeError(f"Places Nearby Search失敗: status={status} / message={data.get('error_message','')}")

    return data.get("results", [])


def place_details(place_id: str):
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

    status = data.get("status")
    if status != "OK":
        raise RuntimeError(f"Place Details失敗: status={status} / message={data.get('error_message','')}")

    return data["result"]


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# =========================
# Helpers (Gemini)
# =========================
def ai_enrich_shops(shops, user_keyword, center_label, priority_label, radius_label_str):
    model = genai.GenerativeModel("models/gemini-2.0-flash")

    candidates = [
        {
            "place_id": s["place_id"],
            "name": s["name"],
            "address": s["address"],
            "rating": s.get("rating"),
            "user_ratings_total": s.get("user_ratings_total"),
            "distance_m": s["distance_m"],
        }
        for s in shops
    ]

    prompt = f"""
あなたは店舗選定アシスタントです。

制約（最重要）：
- 次の「候補店舗リスト」に含まれる店舗以外の店名・住所は絶対に出さないでください。
- 出力は候補の place_id に対する補足情報（reason / reviews）だけを返してください。
- マークダウンや説明文は不要、JSONのみ。

ユーザーの探しているもの: {user_keyword}
検索中心: {center_label}
半径: {radius_label_str}
重視軸: {priority_label}

出力JSON形式：
{{
  "shops": [
    {{
      "place_id": "...",
      "reason": "おすすめ理由（1～3文）",
      "reviews": "口コミ傾向の要約（良い点・悪い点を1～3文）"
    }}
  ]
}}

候補店舗リスト：
{json.dumps(candidates, ensure_ascii=False)}
"""
    resp = model.generate_content(prompt)
    text = resp.text.replace("```json", "").replace("```", "").strip()

    data = json.loads(text)
    enrich_map = {x.get("place_id"): x for x in data.get("shops", [])}

    out = []
    for s in shops:
        extra = enrich_map.get(s["place_id"], {})
        s2 = dict(s)
        s2["reason"] = extra.get("reason", "")
        s2["reviews"] = extra.get("reviews", "")
        out.append(s2)

    return out


# =========================
# Main
# =========================
if st.button("検索") and center and keyword:
    try:
        geo = geocode_address(center)
        if not geo:
            st.stop()

        lat, lng, center_label = geo
        st.success(f"検索中心: {center_label}（半径 {radius_label}）")

        raw = places_nearby(lat, lng, radius_m, keyword)

        if not raw:
            st.warning("該当する店舗が見つかりませんでした。キーワードを変えて試してください。")
            st.stop()

        shops = []
        for item in raw[:10]:  # 取りすぎ防止（費用/速度対策）
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

        if not shops:
            st.warning("店舗情報の取得に失敗しました。別のキーワードでお試しください。")
            st.stop()

        if priority == "近さ重視":
            shops.sort(key=lambda x: x["distance_m"])
        else:
            shops.sort(key=lambda x: (-(x["rating"] or -1), x["distance_m"]))

        shops = shops[:5]

        shops = ai_enrich_shops(
            shops=shops,
            user_keyword=keyword,
            center_label=center_label,
            priority_label=priority,
            radius_label_str=radius_label,
        )

        for s in shops:
            rating = s.get("rating")
            rating_text = f"{rating} / 5" if rating is not None else "評価なし"
            sub = f"⭐ {rating_text}・🧭 {s['distance_m']}m"

            with st.expander(f"🏢 {s['name']}（{sub}）"):
                st.write("📍 **住所**")
                st.write(s["address"] if s.get("address") else "不明")

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
                    query = f"{s.get('name','')} {s.get('address','')}".strip()
                    map_url = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(query)
                    st.link_button("Googleマップで検索", map_url)

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")

elif st.button("検索"):
    st.warning("「検索中心」と「キーワード」を入力してください。")
