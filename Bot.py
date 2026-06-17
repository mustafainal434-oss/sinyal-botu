import os
import logging
import requests
import pandas as pd
import pandas_ta as ta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TIMEFRAME = "4h"
LOOKBACK = 100

def get_all_usdt_pairs():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    data = requests.get(url).json()
    pairs = []
    for s in data["symbols"]:
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING":
            pairs.append(s["symbol"])
    return pairs

def get_klines(symbol, interval, limit):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params)
    if r.status_code != 200:
        raise Exception(f"HTTP {r.status_code}")
    return r.json()

def calculate_indicators(df):
    df["RSI"] = ta.rsi(df["close"], length=14)
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    df["MACD"] = macd["MACD_12_26_9"]
    df["MACD_signal"] = macd["MACDs_12_26_9"]
    df["volume_avg5"] = df["volume"].rolling(5).mean()
    df["volume_ratio"] = df["volume"] / df["volume_avg5"]
    return df

def check_signals(df, symbol):
    last = df.iloc[-1]
    signal = None
    score = 0
    if last["RSI"] < 35 and last["MACD"] > last["MACD_signal"] and last["volume_ratio"] > 1.2:
        signal = "LONG"
        score = 85 if last["RSI"] < 30 else 78
    elif last["RSI"] > 68 and last["MACD"] < last["MACD_signal"] and last["volume_ratio"] < 0.9:
        signal = "SHORT"
        score = 85 if last["RSI"] > 72 else 77
    if signal:
        price = last["close"]
        atr = ta.atr(df["high"], df["low"], df["close"], length=14).iloc[-1]
        if signal == "LONG":
            entry_low = round(price * 0.998, 6)
            entry_high = round(price * 1.002, 6)
            sl = round(price - 1.5 * atr, 6)
            tp1 = round(price + 2 * atr, 6)
            tp2 = round(price + 4 * atr, 6)
        else:
            entry_low = round(price * 0.998, 6)
            entry_high = round(price * 1.002, 6)
            sl = round(price + 1.5 * atr, 6)
            tp1 = round(price - 2 * atr, 6)
            tp2 = round(price - 4 * atr, 6)
        return {
            "symbol": symbol, "signal": signal, "price": price,
            "rsi": round(last["RSI"], 1),
            "entry_low": entry_low, "entry_high": entry_high,
            "sl": sl, "tp1": tp1, "tp2": tp2, "score": score
        }
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Neron Benzeri Sinyal Botu Hazır!\n\n"
        "Komutlar:\n"
        "/tara - Tüm Binance USDT çiftlerini tara\n"
        "/durum - Botun çalışma durumunu kontrol et"
    )

async def durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot çalışıyor, veriler canlı.")

async def tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Tüm Binance USDT piyasası taranıyor... (400+ coin, biraz sürebilir)")
    pairs = get_all_usdt_pairs()
    results = []
    for i, sym in enumerate(pairs, 1):
        try:
            candles = get_klines(sym, TIMEFRAME, LOOKBACK)
            df = pd.DataFrame(candles, columns=[
                "time", "open", "high", "low", "close", "volume",
                "_", "_", "_", "_", "_", "_"
            ])
            df = df[["open", "high", "low", "close", "volume"]].astype(float)
            df = calculate_indicators(df)
            res = check_signals(df, sym)
            if res:
                results.append(res)
        except:
            pass
        if i % 50 == 0:
            try:
                await msg.edit_text(f"🔍 Taranıyor: {i}/{len(pairs)} coin... ({len(results)} sinyal bulundu)")
            except:
                pass

    if not results:
        await msg.edit_text("⚠️ Şu an sinyal veren coin yok.")
        return

    mesaj = "📡 **Güncel Sinyaller**\n\n"
    for r in results:
        emoji = "🟢" if r["signal"] == "LONG" else "🔴"
        mesaj += f"{emoji} **{r['symbol']}** | Fiyat: {r['price']} | RSI: {r['rsi']}\n"
        mesaj += f"Giriş: {r['entry_low']} - {r['entry_high']}\n"
        mesaj += f"SL: {r['sl']} | TP1: {r['tp1']} | TP2: {r['tp2']}\n"
        mesaj += f"Skor: {r['score']}/100\n\n"

    if len(mesaj) > 4000:
        for i in range(0, len(mesaj), 4000):
            await update.message.reply_text(mesaj[i:i+4000], parse_mode="Markdown")
    else:
        await msg.edit_text(mesaj, parse_mode="Markdown")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("durum", durum))
    app.add_handler(CommandHandler("tara", tara))
    app.run_polling()
