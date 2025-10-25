import ccxt
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime
import logging
import schedule
import os
import random

# =============================
# CONFIGURAÇÃO DE LOGGING CLOUD
# =============================
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =============================
# VARIÁVEIS DE AMBIENTE
# =============================
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

CRYPTO_SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'BNB/USDT',
    'SOL/USDT', 'DOGE/USDT', 'TRX/USDT', 'ADA/USDT',
    'LINK/USDT', 'AVAX/USDT'
]

# =============================
# CLASSE PRINCIPAL
# =============================
class CryptoAnalyzer:
    def __init__(self):
        self.exchange = ccxt.binance({
            'rateLimit': 1200,
            'enableRateLimit': True,
            'timeout': 30000,
        })
        self.last_analysis = {}
        self.message_buffer = []
        logger.info("✅ Inicialização concluída.")

    # -----------------------------
    # Envio de mensagens no Telegram
    # -----------------------------
    def send_telegram_message(self, message):
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.error("⚠️ Variáveis TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID ausentes.")
            return
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                logger.error(f"Erro ao enviar mensagem: {response.status_code} - {response.text}")
            else:
                logger.info("📤 Mensagem enviada ao Telegram.")
        except Exception as e:
            logger.error(f"Erro Telegram: {e}")

    # -----------------------------
    # Buffer de mensagens (envio consolidado)
    # -----------------------------
    def flush_messages(self):
        if self.message_buffer:
            full_message = "\n\n".join(self.message_buffer)
            self.send_telegram_message(full_message)
            self.message_buffer = []

    # -----------------------------
    # RSI com EMA (mais preciso)
    # -----------------------------
    def calculate_rsi(self, prices, period=14):
        if len(prices) < period:
            return 50
        deltas = np.diff(prices)
        gain = np.where(deltas > 0, deltas, 0)
        loss = np.where(deltas < 0, -deltas, 0)
        roll_up = pd.Series(gain).ewm(span=period).mean()
        roll_down = pd.Series(loss).ewm(span=period).mean()
        rs = roll_up / roll_down
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not rsi.empty else 50

    # -----------------------------
    # Fetch com retry automático
    # -----------------------------
    def get_ohlcv_data(self, symbol, timeframe='1h', limit=100, retries=3):
        for attempt in range(retries):
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                return df
            except Exception as e:
                wait = 2 ** attempt + random.random()
                logger.warning(f"Tentativa {attempt+1}/{retries} falhou para {symbol}: {e}. Retentando em {wait:.1f}s...")
                time.sleep(wait)
        logger.error(f"❌ Falha definitiva ao buscar {symbol} após {retries} tentativas.")
        return None

    # -----------------------------
    # Análise individual
    # -----------------------------
    def analyze_crypto(self, symbol):
        df = self.get_ohlcv_data(symbol)
        if df is None or len(df) < 50:
            return None

        last_timestamp = df['timestamp'].iloc[-1]
        if self.last_analysis.get(symbol) == last_timestamp:
            logger.info(f"⏸️ {symbol} sem nova vela, ignorado.")
            return None

        prices = df['close'].tolist()
        rsi = self.calculate_rsi(prices)
        signal = "NEUTRO"
        if rsi <= 30:
            signal = "COMPRA"
        elif rsi >= 70:
            signal = "VENDA"

        self.last_analysis[symbol] = last_timestamp

        return {
            'symbol': symbol,
            'price': prices[-1],
            'rsi': rsi,
            'signal': signal,
            'timestamp': datetime.now()
        }

    # -----------------------------
    # Análise de todas as criptos
    # -----------------------------
    def analyze_all_cryptos(self):
        logger.info("🔍 Iniciando nova análise de mercado...")
        signals_found = 0
        rsi_values = []

        for symbol in CRYPTO_SYMBOLS:
            try:
                analysis = self.analyze_crypto(symbol)
                if not analysis:
                    continue

                rsi = analysis['rsi']
                signal = analysis['signal']
                price = analysis['price']
                rsi_values.append(rsi)

                logger.info(f"{symbol} | RSI: {rsi:.2f} | {signal}")

                if signal != "NEUTRO":
                    msg = f"""
{'🟢' if signal == 'COMPRA' else '🔴'} <b>{signal}</b>

<b>Moeda:</b> {symbol}
<b>Preço:</b> ${price:.4f}
<b>RSI:</b> {rsi:.2f}

<b>Horário:</b> {analysis['timestamp'].strftime('%d/%m/%Y %H:%M')}
"""
                    self.message_buffer.append(msg)
                    signals_found += 1

                time.sleep(1)  # respeita o rate limit global

            except Exception as e:
                logger.error(f"Erro analisando {symbol}: {e}")

        # ---- Tendência geral ----
        if rsi_values:
            avg_rsi = np.mean(rsi_values)
            if avg_rsi <= 35:
                trend = "🟢 <b>Mercado sobrevendido</b> (potencial reversão de alta)"
            elif avg_rsi >= 65:
                trend = "🔴 <b>Mercado sobrecomprado</b> (potencial correção)"
            else:
                trend = "⚪ <b>Mercado neutro</b> (sem pressão significativa)"

            summary = f"\n📊 <b>Tendência Geral:</b>\nRSI médio: {avg_rsi:.2f}\n{trend}"
            self.message_buffer.append(summary)
            logger.info(summary.replace("<b>", "").replace("</b>", ""))

        if signals_found or rsi_values:
            self.flush_messages()
        else:
            logger.info("Nenhum sinal relevante encontrado.")

# =============================
# FUNÇÃO PRINCIPAL
# =============================
def main():
    analyzer = CryptoAnalyzer()

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ Variáveis de ambiente do Telegram não configuradas.")
        return

    analyzer.send_telegram_message("🤖 <b>Bot Iniciado na Nuvem (Railway)</b>")
    logger.info("🤖 Bot iniciado na nuvem com sucesso!")

    start_time = datetime.now()
    schedule.every(15).minutes.do(analyzer.analyze_all_cryptos)

    while True:
        try:
            schedule.run_pending()
            uptime = datetime.now() - start_time
            logger.info(f"⏱️ Uptime: {uptime}")
            time.sleep(60)
        except Exception as e:
            logger.error(f"Erro no loop principal: {e}")
            time.sleep(300)

# =============================
# EXECUÇÃO
# =============================
if __name__ == "__main__":
    main()
