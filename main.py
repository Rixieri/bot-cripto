import os
import time
import logging
import pandas as pd
import numpy as np
import requests
from datetime import datetime
from binance.client import Client

# =============================
# LOGS
# =============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# =============================
# TELEGRAM
# =============================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logging.error("❌ Variáveis do Telegram não configuradas!")
    exit(1)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logging.error(f"Erro Telegram {response.status_code}: {response.text}")
        else:
            logging.info("Mensagem enviada ao Telegram")
    except Exception as e:
        logging.error(f"Erro enviando Telegram: {e}")

# =============================
# CLIENTE BINANCE
# =============================
client = Client()  # público

# =============================
# MOEDAS E TIMEFRAMES
# =============================
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT",
    "SOLUSDT", "DOGEUSDT", "TRXUSDT", "ADAUSDT",
    "LINKUSDT", "AVAXUSDT"
]

TIMEFRAMES = {
    "1h": Client.KLINE_INTERVAL_1HOUR,
    "4h": Client.KLINE_INTERVAL_4HOUR
}
LIMIT = 200

# =============================
# INDICADORES
# =============================
def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def rsi(close, period=14):
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# =============================
# SUPORTE / RESISTÊNCIA
# =============================
def detect_support_resistance(df, window=5):
    highs, lows = df["high"], df["low"]
    resistance, support = [], []
    for i in range(window, len(df) - window):
        if highs[i] == highs[i - window:i + window].max():
            resistance.append(highs[i])
        if lows[i] == lows[i - window:i + window].min():
            support.append(lows[i])
    def clean(levels):
        cleaned = []
        for lvl in sorted(levels):
            if not cleaned or abs(lvl - cleaned[-1]) / cleaned[-1] > 0.005:
                cleaned.append(lvl)
        return cleaned
    return clean(support), clean(resistance)

def detect_zone(df, rsi_val, price):
    supports, resistances = detect_support_resistance(df)
    near_support = any(abs(price - s) / s < 0.003 for s in supports)
    near_resistance = any(abs(price - r) / r < 0.003 for r in resistances)
    if rsi_val >= 70 and near_resistance:
        return "🔴 ALERTA VENDA"
    elif rsi_val <= 30 and near_support:
        return "🟢 ALERTA COMPRA"
    return None

# =============================
# ANÁLISE DE MOEDA
# =============================
def analyze_symbol(symbol):
    alerts = []
    rsi_list = []
    for tf_name, tf_interval in TIMEFRAMES.items():
        try:
            klines = client.futures_klines(symbol=symbol, interval=tf_interval, limit=LIMIT)
            df = pd.DataFrame(klines, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "trades",
                "taker_buy_base", "taker_buy_quote", "ignore"
            ])
            df["close"] = df["close"].astype(float)
            df["high"] = df["high"].astype(float)
            df["low"] = df["low"].astype(float)

            price = df["close"].iloc[-1]
            rsi_val = rsi(df["close"]).iloc[-1]
            rsi_list.append(rsi_val)

            signal = detect_zone(df, rsi_val, price)
            if not signal:
                if rsi_val >= 70:
                    signal = "🔴 ALERTA VENDA"
                elif rsi_val <= 30:
                    signal = "🟢 ALERTA COMPRA"

            if signal:
                alerts.append(f"""
{signal} ({tf_name})
Moeda: {symbol}
Preço: ${price:.4f}
RSI: {rsi_val:.2f}
Horário: {datetime.now().strftime('%d/%m/%Y %H:%M')}
""")
        except Exception as e:
            logging.error(f"Erro analisando {symbol} {tf_name}: {e}")

    # RSI médio entre 1h e 4h
    avg_rsi = np.mean(rsi_list)
    if avg_rsi <= 35:
        trend = "🟢 Mercado sobrevendido (potencial reversão)"
    elif avg_rsi >= 65:
        trend = "🔴 Mercado sobrecomprado (potencial correção)"
    else:
        trend = "⚪ Mercado neutro (sem pressão significativa)"

    return alerts, avg_rsi, trend

# =============================
# ANÁLISE DE TODAS AS MOEDAS
# =============================
def analyze_all():
    all_alerts = []
    rsi_values = []
    for symbol in SYMBOLS:
        alerts, avg_rsi, trend = analyze_symbol(symbol)
        all_alerts.extend(alerts)
        rsi_values.append(avg_rsi)

    # Tendência geral final
    if rsi_values:
        total_avg_rsi = np.mean(rsi_values)
        if total_avg_rsi <= 35:
            overall_trend = "🟢 Mercado sobrevendido (potencial reversão)"
        elif total_avg_rsi >= 65:
            overall_trend = "🔴 Mercado sobrecomprado (potencial correção)"
        else:
            overall_trend = "⚪ Mercado neutro (sem pressão significativa)"
        all_alerts.append(f"\n📊 Tendência Geral:\nRSI médio: {total_avg_rsi:.2f}\n{overall_trend}")

    if all_alerts:
        send_telegram_message("\n".join(all_alerts))
    else:
        logging.info("Nenhum sinal relevante neste ciclo.")

# =============================
# LOOP PRINCIPAL 15 MINUTOS
# =============================
def main():
    while True:
        logging.info("🔍 Iniciando análise das criptomoedas...")
        analyze_all()
        logging.info("⏳ Aguardando 15 minutos para próximo ciclo...")
        time.sleep(900)  # 15 minutos

if __name__ == "__main__":
    main()
