import os
import time
import logging
import pandas as pd
import numpy as np
import requests
from datetime import datetime
from binance.client import Client

# =============================
# CONFIGURAÇÃO DE LOGS
# =============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# =============================
# VARIÁVEIS DE AMBIENTE
# =============================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logging.error("❌ Variáveis de ambiente do Telegram não configuradas!")
    exit(1)

# =============================
# FUNÇÃO PARA ENVIAR TELEGRAM
# =============================
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
# CLIENTE PÚBLICO BINANCE
# =============================
client = Client()  # sem API key

# =============================
# LISTA DE MOEDAS
# =============================
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT",
    "SOLUSDT", "DOGEUSDT", "TRXUSDT", "ADAUSDT",
    "LINKUSDT", "AVAXUSDT"
]
INTERVAL = Client.KLINE_INTERVAL_15MINUTE
LIMIT = 200

# =============================
# FUNÇÕES DE INDICADORES
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
# DETECÇÃO DE SUPORTE/RESISTÊNCIA
# =============================
def detect_support_resistance(df, window=5):
    highs, lows = df["high"], df["low"]
    resistance, support = [], []

    for i in range(window, len(df) - window):
        high_slice = highs[i - window:i + window]
        low_slice = lows[i - window:i + window]

        if highs[i] == high_slice.max():
            resistance.append(highs[i])
        if lows[i] == low_slice.min():
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
# ANÁLISE DE TODAS AS MOEDAS
# =============================
def analyze_all():
    alerts = []
    rsi_values = []

    for symbol in SYMBOLS:
        try:
            klines = client.futures_klines(symbol=symbol, interval=INTERVAL, limit=LIMIT)
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
            rsi_values.append(rsi_val)

            signal = detect_zone(df, rsi_val, price)
            if not signal:
                if rsi_val >= 70:
                    signal = "🔴 ALERTA VENDA"
                elif rsi_val <= 30:
                    signal = "🟢 ALERTA COMPRA"

            if signal:
                alerts.append(f"""
{signal}
Moeda: {symbol}
Preço: ${price:.4f}
RSI: {rsi_val:.2f}
Horário: {datetime.now().strftime('%d/%m/%Y %H:%M')}
""")
        except Exception as e:
            logging.error(f"Erro analisando {symbol}: {e}")

    # Tendência geral
    if rsi_values:
        avg_rsi = np.mean(rsi_values)
        if avg_rsi <= 35:
            trend = "🟢 Mercado sobrevendido (potencial reversão)"
        elif avg_rsi >= 65:
            trend = "🔴 Mercado sobrecomprado (potencial correção)"
        else:
            trend = "⚪ Mercado neutro (sem pressão significativa)"
        alerts.append(f"\n📊 Tendência Geral:\nRSI médio: {avg_rsi:.2f}\n{trend}")

    if alerts:
        send_telegram_message("\n".join(alerts))
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
