import ccxt
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime
import logging
import schedule
import os

# Configurar logging para cloud
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurações (usando variáveis de ambiente)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

CRYPTO_SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'BNB/USDT', 
    'SOL/USDT', 'DOGE/USDT', 'TRX/USDT', 'ADA/USDT',
    'LINK/USDT', 'AVAX/USDT'
]

class CryptoAnalyzer:
    def __init__(self):
        self.exchange = ccxt.binance({
            'rateLimit': 1200,
            'enableRateLimit': True,
            'timeout': 30000,
        })
        
    def send_telegram_message(self, message):
        """Envia mensagem para o Telegram"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.error("Variáveis de ambiente não configuradas")
            return
            
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                logger.info("✅ Mensagem enviada")
            else:
                logger.error(f"❌ Erro: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Erro Telegram: {e}")
    
    def calculate_rsi(self, prices, period=14):
        """Calcula RSI simplificado"""
        if len(prices) < period:
            return 50
            
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gains = pd.Series(gains).rolling(window=period).mean()
        avg_losses = pd.Series(losses).rolling(window=period).mean()
        
        rs = avg_gains / avg_losses
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not rsi.empty and not pd.isna(rsi.iloc[-1]) else 50

    def get_ohlcv_data(self, symbol, timeframe='1h', limit=100):
        """Obtém dados da exchange"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            return df
        except Exception as e:
            logger.error(f"Erro ao buscar {symbol}: {e}")
            return None

    def analyze_crypto(self, symbol):
        """Analisa uma criptomoeda"""
        df = self.get_ohlcv_data(symbol)
        if df is None or len(df) < 50:
            return None

        prices = df['close'].tolist()
        rsi = self.calculate_rsi(prices)
        
        # Análise simplificada para cloud
        signal = "NEUTRO"
        if rsi <= 30:
            signal = "COMPRA"
        elif rsi >= 70:
            signal = "VENDA"
        
        analysis = {
            'symbol': symbol,
            'price': prices[-1],
            'rsi': rsi,
            'signal': signal,
            'timestamp': datetime.now()
        }
        
        return analysis

    def analyze_all_cryptos(self):
        """Analisa todas as criptomoedas"""
        logger.info("🔍 Iniciando análise...")
        
        for symbol in CRYPTO_SYMBOLS:
            try:
                analysis = self.analyze_crypto(symbol)
                if analysis and analysis['signal'] != "NEUTRO":
                    message = f"""
{'🟢' if analysis['signal'] == 'COMPRA' else '🔴'} <b>ALERTA {analysis['signal']}</b>

<b>Moeda:</b> {analysis['symbol']}
<b>Preço:</b> ${analysis['price']:.4f}
<b>RSI:</b> {analysis['rsi']:.2f}

<b>Horário:</b> {analysis['timestamp'].strftime('%d/%m/%Y %H:%M')}
"""
                    self.send_telegram_message(message)
                    logger.info(f"Sinal {analysis['signal']} para {analysis['symbol']}")
                
                time.sleep(1)  # Rate limit
                
            except Exception as e:
                logger.error(f"Erro em {symbol}: {e}")
                continue

def main():
    """Função principal otimizada para cloud"""
    analyzer = CryptoAnalyzer()
    
    # Verificar se variáveis estão configuradas
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ Variáveis de ambiente não configuradas!")
        return
    
    # Mensagem de início
    analyzer.send_telegram_message("🤖 <b>Bot Iniciado na Nuvem!</b>")
    logger.info("🤖 Bot iniciado na nuvem!")
    
    # Configurar schedule
    schedule.every(30).minutes.do(analyzer.analyze_all_cryptos)
    
    # Loop principal
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Verificar a cada minuto
        except Exception as e:
            logger.error(f"Erro no loop principal: {e}")
            time.sleep(300)  # Espera 5 minutos em caso de erro

if __name__ == "__main__":
    main()