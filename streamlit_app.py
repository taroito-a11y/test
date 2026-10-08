import math
import json
import urllib.parse

import requests
import streamlit as st
import google.generativeai as genai


GEMINI_MODEL = "models/gemini-3.8-flash"


st.set_page_config(page_title="店舗検索アプリ", page_icon="📍")
st.title("📍 生成AIプレイス検索")


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
q = st.text_input(
    "自由に入力（場所＋探したい店＋条件）",
    placeholder="例：早稲田大学の近くで静かなカフェ。評価が高いところがいい"
)

col1, col2 = st.columns(2)
with col1:
    radius_label = st.radio("検索半径", ["500m", "1km", "2km"], horizontal=True)
with col2:
    priority = st.radio("重視するポイント", ["近さ重視", "評価重視"], horizontal=True)

radius_m = {"500m": 500, "1km": 1000, "2km": 2000}[radius_label]

st.caption("※ 店舗名・住所・評価・距離はGoogle Placesの実データです。AIは地点/キーワード抽出・要約・理由のみ生成します。")


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
def ai_extract_search_params(user_text: str, ui_priority: str, ui_radius_label: str):
    model = genai.GenerativeModel(GEMINI_MODEL)
    prompt = f"""
あなたは検索クエリ分解器です。
ユーザーの自由記述から「検索中心（Geocodingに投げられる地名・駅名・施設名）」と
「Placesのkeyword（店種/条件のキーワード）」を抽出してください。

制約：
- 出力はJSONのみ（マークダウン禁止）
- center は、可能な限り固有名詞を含む短い文字列（例：早稲田大学、新宿駅、渋谷区役所）
- keyword は、Placesのkeywordに適した短い文字列（例：カフェ 静か、スーパー、ラーメン）
- もし場所が不明確なら、center を空文字にせず「ユーザー入力から推定できる最も中心に近い語」を入れてください
- ui_priority / ui_radius は参考情報（中心/keyword抽出の補助）として扱って良い

追加情報：
- ui_priority: {ui_priority}
- ui_radius: {ui_radius_label}

出力JSON形式：
{{
  "center": "…",
  "keyword": "…",
  "constraints": {{
    "must": ["…", "…"],
    "nice_to_have": ["…"]
  }}
}}

ユーザー入力：
{user_text}
"""
    resp = model.generate_content(prompt)
    text = resp.text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def ai_enrich_shops(shops, user_text, extracted, center_label, priority_label, radius_label_str):
    model = genai.GenerativeModel(GEMINI_MODEL)

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

ユーザー入力：
{user_text}

抽出結果：
center={extracted.get("center","")}
keyword={extracted.get("keyword","")}
constraints={json.dumps(extracted.get("constraints", {}), ensure_ascii=False)}

検索中心（正規化）: {center_label}
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
if st.button("検索") and q:
    try:
        with st.spinner("入力内容を解析中..."):
            extracted = ai_extract_search_params(q, priority, radius_label)

        st.info("AI抽出結果")
        st.write(
            {
                "center": extracted.get("center", ""),
                "keyword": extracted.get("keyword", ""),
                "constraints": extracted.get("constraints", {}),
            }
        )

        center_text = (extracted.get("center") or "").strip()
        keyword_text = (extracted.get("keyword") or "").strip()

        if not center_text or not keyword_text:
            st.error("検索に必要な情報（中心/キーワード）の抽出に失敗しました。入力を少し具体化してください。")
            st.stop()

        geo = geocode_address(center_text)
        if not geo:
            st.stop()

        lat, lng, center_label = geo
        st.success(f"検索中心: {center_label}（半径 {radius_label}）")

        with st.spinner("実在店舗を検索中（Google Places）..."):
            raw = places_nearby(lat, lng, radius_m, keyword_text)

        if not raw:
            st.warning("該当する店舗が見つかりませんでした。別の言い方（例：喫茶店/コーヒー/ベーカリー）も試してください。")
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

        with st.spinner("AIが理由・口コミ傾向を生成中..."):
            shops = ai_enrich_shops(
                shops=shops,
                user_text=q,
                extracted=extracted,
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
