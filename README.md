# 周辺検索アプリ

Google Maps PlatformとGeminiを使ったStreamlitアプリです。

## 機能

- 自然文による周辺のお店検索
- マンション名から引っ越し先の周辺環境を調査
  - 駅
  - スーパー
  - コンビニ
  - 薬局
  - 病院・クリニック
  - 保育園・学校
  - 公園
  - 警察

周辺環境チェックはGoogle Maps Platformのみを使用するため、Geminiのクレジットがなくても利用できます。

## Streamlit Secrets

```toml
GEMINI_API_KEY = "..."
GOOGLE_MAPS_API_KEY = "..."
```

お店検索には両方のキー、周辺環境チェックには`GOOGLE_MAPS_API_KEY`だけが必要です。
