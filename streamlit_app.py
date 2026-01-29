from flask import Flask, request, jsonify
import json, urllib.parse
from google import genai
from google.genai import types

API_KEY = "AIzaSyDe9J4dzzJfl9swsYBgMmq3br6ZzcCixhQ"
client = genai.Client(api_key=API_KEY)

app = Flask(__name__)

@app.route("/search", methods=["POST"])
def search():
    user_input = request.json["query"]

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"""
        以下の文章から対象の地域を特定し、その周辺の店舗【5件のみ】厳選してJSONで出力してください。
        文章：{user_input}
        """,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_maps=types.GoogleMaps())]
        )
    )

    data = json.loads(response.text)
    location = data["detected_location"]

    for shop in data["shops"]:
        q = f'{shop["name"]} {location}'
        shop["map_url"] = (
            "https://www.google.com/maps/search/?api=1&query="
            + urllib.parse.quote(q)
        )

    return jsonify(data)

if __name__ == "__main__":
    app.run()
