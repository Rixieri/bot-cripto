import os
import math
import time
import asyncio
import logging
from datetime import datetime
import pandas as pd
import numpy as np
from binance.client import Client
from binance.enums import *

# Configurações de log
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

class BinanceSignalValidator:
    def __init__(self):
        self.client = Client(
            api_key=os.getenv("BINANCE_API_KEY"),
            api_secret=os.getenv("BINANCE_API_SECRET"),
            testnet=False  # Altere para True se quiser usar testnet
        )
        self.symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        self.interval = Client.KLINE_INTERVAL_15MINUTE
        self.limit = 200

    # ======================
    # === INDICADORES ====
    # ======================
    def ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()

    def macd(self, close):
        ema12 = self.ema(close, 12)
        ema26 = self.ema(close, 26)
        macd_line = ema12 - ema26
        signal_line = self.ema(macd_line, 9)
        hist = macd_line - signal_line
        return macd_line, signal_line, hist

    def rsi(self, close, period=14):
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    # ================================
    # === SUPORTE / RESISTÊNCIA ====
    # ================================
    def detect_support_resistance(self, df, window=5):
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
            if not levels:
                return []
            clean_list = []
            for lvl in sorted(levels):
                if not clean_list or abs(lvl - clean_list[-1]) / clean_list[-1] > 0.005:
                    clean_list.append(lvl)
            return clean_list

        return clean(support), clean(resistance)

    def detect_zone(self, df, rsi, price):
        supports, resistances = self.detect_support_resistance(df)
        near_support = any(abs(price - s) / s < 0.003 for s in supports)
        near_resistance = any(abs(price - r) / r < 0.003 for r in resistances)

        if rsi >= 70 and near_resistance:
            return "🟥 SOBRECOMPRA em RESISTÊNCIA"
        elif rsi <= 30 and near_support:
            return "🟩 SOBREVENDA em SUPORTE"
        return None

    # ======================
    # === ANÁLISE ====
    # ======================
    async def analyze_symbol(self, symbol):
        try:
            klines = self.client.get_klines(
                symbol=symbol, 
                interval=self.interval, 
                limit=self.limit
            )
            
            df = pd.DataFrame(klines, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "trades",
                "taker_buy_base", "taker_buy_quote", "ignore"
            ])
            
            # Converter para float
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)

            close = df["close"]
            ema20 = self.ema(close, 20)
            rsi_series = self.rsi(close)
            rsi_val = rsi_series.iloc[-1] if not rsi_series.empty else 50
            macd_line, signal_line, hist = self.macd(close)

            price = close.iloc[-1]
            zone = self.detect_zone(df, rsi_val, price)

            trend = "⬆️ Alta" if ema20.iloc[-1] > ema20.iloc[-2] else "⬇️ Baixa"
            macd_status = "Bullish" if macd_line.iloc[-1] > signal_line.iloc[-1] else "Bearish"

            signal = None
            if rsi_val >= 70:
                signal = "SOBRECOMPRA"
            elif rsi_val <= 30:
                signal = "SOBREVENDA"
            elif zone:
                signal = "ALERTA"

            msg = f"""
📊 {symbol}
💰 Preço: {price:.2f} USDT
📈 RSI: {rsi_val:.2f}
📊 MACD: {macd_status}
📉 Tendência EMA20: {trend}
"""
            if zone:
                msg += f"\n⚠️ {zone}\n"
            elif signal:
                msg += f"\n⚠️ {signal}\n"

            logging.info(msg.strip())
            
        except Exception as e:
            logging.error(f"Erro analisando {symbol}: {e}")

    async def run(self):
        while True:
            logging.info("Iniciando análise dos símbolos...")
            tasks = [self.analyze_symbol(sym) for sym in self.symbols]
            await asyncio.gather(*tasks)
            logging.info("Análise concluída. Aguardando próximo ciclo...")
            await asyncio.sleep(60)  # intervalo entre análises


if __name__ == "__main__":
    validator = BinanceSignalValidator()
    asyncio.run(validator.run())