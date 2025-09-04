# 🚤 Boatrace EV Prediction & Auto-Betting System

## 概要
本システムは、競艇（ボートレース）のレースデータ・オッズ情報を収集し、  
期待値（EV = Expected Value）に基づいた自動的な舟券購入を行うシステムです。  

- **目的**: 長期的に資金を増加させる「正の期待値ベット」を自動実行  
- **特徴**:
  - Docker コンテナベースのモジュール構成  
  - FastAPI による推論 API (`ev-engine`)  
  - odds collector によるオッズ収集  
  - Postgres + Redis によるストレージ / キャッシュ  
  - EV計算・ステーク配分（線形配分 / ケリー基準 / 縮小ケリー）  

---

## システム構成
```
boatrace-ev/
├── docker-compose.dev.yml # 開発用 compose 設定
├── .env.sample # 環境変数サンプル
├── services/
│ ├── ev-engine/ # 期待値計算 & 注文 API (FastAPI)
│ │ └── app/
│ │ └── main.py
│ └── odds-collector/ # オッズ収集スクリプト
│ └── main.py
├── db/
│ └── schema.sql # Postgres テーブル定義
└── README.md
```

pgsql
コードをコピーする

### コンテナ一覧
- **ev-engine**: FastAPI による API サーバ  
  - `/health` ヘルスチェック  
  - `/predict` EV計算 & 注文候補の記録  
- **odds-collector**: ボートレースWebサイトからオッズを定期収集  
- **postgres**: 注文履歴・オッズ保存用 RDB  
- **redis**: キャッシュ・ジョブキュー  

---

## データベース設計
### 注文テーブル `orders`
```
CREATE TABLE IF NOT EXISTS orders (
  id BIGSERIAL PRIMARY KEY,
  race_id TEXT NOT NULL,
  bet_type TEXT NOT NULL,
  selection TEXT NOT NULL,     -- 例: '1-2-3'
  amount INTEGER NOT NULL,     -- 購入金額 (JPY)
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL,        -- requested/accepted/rejected/settled
  provider_response JSONB,
  idempotency_key TEXT NOT NULL,
  UNIQUE (idempotency_key)
);
```

### 冪等性 (idempotency)
同じレース・同じ選択肢に重複発注しないよう `idempotency_key` を設定

### Dryrunモード
実注文せず「候補を記録」するだけの検証モードあり

## EV計算ロジック
**EVとは？**  
\[
EV = p \times odds
\]

- **p**: 自作モデル or implied probability（市場オッズ由来の確率）  
- **odds**: 払戻倍率（例: オッズ20倍 → 20.0）  

EV > 1 → 長期的にプラス期待値

### 確率の計算
- `p_model`: 機械学習モデルによる勝率予測  
- `p_implied`: オッズ逆算の暗黙確率（正規化済）  

混合式:
\[
p = \alpha \cdot p_{model} + (1-\alpha) \cdot p_{implied}
\]

## ステーク配分ロジック
### 線形配分
- EV − 1 を重みとし、予算を比例配分  
- EV ≤ 1 の候補には 0 円  
- 100円単位に丸め  

### 縮小ケリー
- ケリー基準の賭け比率 \( f^* \) を計算  
- 実際は \( f = \lambda f^* \) （λ=0.25, 0.5 など縮小）  
- リスクを抑えつつ資金成長を狙う  

### ソフトマックス配分
- 候補のスコアを指数化し重み付け  

\[
w_i = \frac{e^{s_i/\tau}}{\sum_j e^{s_j/\tau}}
\]

- 温度パラメータ τ で集中度を調整  

## 利用方法
### 開発環境起動
```
docker compose -f docker-compose.dev.yml up --build -d
```

### API確認
```
curl http://127.0.0.1:8000/health
```

### 推論リクエスト
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "race_id":"20250915_OMURA_12",
    "snapshot_ts":"2025-09-15T12:30:00Z",
    "bet_type":"TRI",
    "top_k":2
  }'

## 今後の拡張

- odds-collector を本番環境に対応（安定クローラ + タスクスケジューラ）

- ev-engine に学習済みモデルを組み込み

- 注文ステータス管理（accepted/settled更新）

- ROI（回収率）自動集計ダッシュボード

- Kubernetes / Linux サーバへの本番移行