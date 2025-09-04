# services/ev-engine/app/main.py
from fastapi import FastAPI
from pydantic import BaseModel
import os, hashlib
from psycopg_pool import ConnectionPool
from datetime import datetime

app = FastAPI()

DATABASE_URL=os.getenv("DATABASE_URL","postgresql://app:app@postgres:5432/boatrace")
ORDER_MODE=os.getenv("ORDER_MODE","dryrun")  # dryrun | manual | auto
EV_MIN       = float(os.getenv("EV_MIN", "1.05"))     # EVの下限
ALPHA        = float(os.getenv("ALPHA", "0.5"))       # 確率の混合重み(1=モデル、0=implied)
MAX_STAKE    = int(os.getenv("MAX_STAKE_PER_RACE", "2000"))


# ---- DBプール（プロセス共有） ----
pool = ConnectionPool(conninfo=DATABASE_URL, max_size=10, kwargs={"prepare_threshold": 0})

@app.get("/health")
def health():
    try:
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        ok = True
    except Exception:
        ok = False
    return{"ok": ok, "mode": ORDER_MODE}

@app.get("/")
def root():
    return {"msg": "ev-engine up"}


class PredictIn(BaseModel):
    race_id: str
    snapshot_ts: str
    bet_type: str ="TRI"
    top_k: int=2
    
# ====== DB: 最新スナップショットを取得 ======
def resolve_snapshot_ts(conn, race_id: str, bet_type: str, ts_iso: str) -> datetime:
    sql = """
    SELECT MAX(snapshot_ts)
    FROM odds_ticks
    WHERE race_id=%s AND bet_type=%s AND snapshot_ts <= %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (race_id, bet_type, ts_iso))
        row = cur.fetchone()
        if not row or not row[0]:
            raise HTTPException(status_code=404, detail="no odds snapshot <= requested ts")
        return row[0]  # datetime(tz)

def fetch_market(conn, race_id: str, bet_type: str, snap_ts) -> list[dict]:
    sql = """
    SELECT selection, odds
    FROM odds_ticks
    WHERE race_id=%s AND bet_type=%s AND snapshot_ts=%s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (race_id, bet_type, snap_ts))
        rows = cur.fetchall()
    return [{"selection": r[0], "odds": float(r[1])} for r in rows]

# ====== 確率の仮モデル（暫定） ======
def implied_probs(market: list[dict]) -> list[float]:
    # オッズからの暗黙確率（overroundは正規化で除去）
    invs = []
    for m in market:
        if m["odds"] <= 0:
            invs.append(0.0)
        else:
            invs.append(100.0 / m["odds"])  # 配当を倍率に直すと 100/odds が近似確率の逆数
    s = sum(invs) or 1.0
    return [x / s for x in invs]

def simple_model_probs(market: list[dict]) -> list[float]:
    # 簡易: オッズの低い（人気）方を少しだけ強める
    # odds が小さいほど weight を高くする単純重み（デモ用）
    weights = []
    for m in market:
        w = 1.0 / max(m["odds"], 1e-6)
        weights.append(w)
    s = sum(weights) or 1.0
    return [w / s for w in weights]

def mix_probs(p_model: list[float], p_impl: list[float], alpha: float) -> list[float]:
    return [max(0.0, min(1.0, alpha*pm + (1.0-alpha)*pi)) for pm, pi in zip(p_model, p_impl)]
    
# 例用のダミー推論
def dummy_candidates():
    return [
        {"selection": "1-2-3", "p": 0.10, "odds": 18.5, "ev": 1.85, "stake": 500},
        {"selection": "1-3-2", "p": 0.08, "odds": 20.0, "ev": 1.60, "stake": 500},
    ]

def make_idempotency_key(race_id: str, bet_type: str, selection: str, amount: int, snapshot_ts: str) -> str:
    raw = f"{race_id}|{bet_type}|{selection}|{amount}|{snapshot_ts}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def insert_orders(race_id: str, bet_type: str, snapshot_ts: str, candidates: list, status: str = "requested"):
    """
    candidates の各要素: {selection, stake, ...}
    返り値: [{"selection":..., "amount":..., "inserted": True/False, "order_id": int|None}, ...]
    """
    sql = """
    INSERT INTO orders (race_id, bet_type, selection, amount, status, idempotency_key)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING id;
    """
    results = []
    with pool.connection() as conn, conn.cursor() as cur:
        for c in candidates:
            selection=c["selection"]
            amount=int(c.get("stake",0))
            if amount <= 0:
                results.append({"selection": selection, "amount": amount, "inserted": False, "order_id": None, "reason": "amount<=0"})
                continue
            idem = make_idempotency_key(race_id, bet_type, selection, amount, snapshot_ts)
            cur.execute(sql, (race_id, bet_type, selection, amount, status,idem))
            row = cur.fetchone()
            if row:
                results.append({"selection": selection, "amount": amount, "inserted": True,  "order_id": row[0]})
            else:
                # 既に同一idempotency_keyの注文がある（重複）
                results.append({"selection": selection, "amount": amount, "inserted": False, "order_id": None, "reason": "duplicate"})
        conn.commit()
    return results
                
@app.post("/predict")
def predict(inp: PredictIn):
    # 本来は DB からオッズを読み → p×odds/100 でEV計算
    candidates = dummy_candidates()[: inp.top_k]
    
    # dryrun/autoに関わらず「注文候補の記録だけ」は同じテーブルでOK
    inserted = insert_orders(
        race_id=inp.race_id,
        bet_type=inp.bet_type,
        snapshot_ts=inp.snapshot_ts,
        candidates=candidates,
        status="requested"  # dryrunはrequestedでOK（実発注は別フローで accepted に）
    )
    
    return {
        "candidates": candidates,
        "orders_insert": inserted,
        "meta": {"mode": ORDER_MODE}
    }