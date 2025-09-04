from loguru import logger
import os, time

DEADLINE_BUFFER = int(os.getenv("DEADLINE_BUFFER_SEC", "20"))

def fetch_odds_once():
    # TODO: 公式の取得手段/フィードを叩く
    # TODO: 取得データに厳密な timestamp を付与
    # TODO: Postgres/Redisに保存（抜けや順序入替の検出も）
    logger.info("Fetched odds snapshot")
    return True

def main_loop():
    logger.info("odds-collector started (buffer={}s)", DEADLINE_BUFFER)
    while True:
        try:
            fetch_odds_once()
        except Exception as e:
            logger.exception("collector error: {}", e)
        time.sleep(5)  # 例: 5秒間隔。締切前は短縮などのチューニングを

if __name__ == "__main__":
    main_loop()
