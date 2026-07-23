# Quick Start Guide - Kronos TradingView Interface

## 🚀 Get Started in 5 Minutes

### Step 1: Install Dependencies
```bash
cd webui
pip install -r requirements_tradingview.txt
```

### Step 2: Start the Server
```bash
python app_tradingview.py
```

You should see:
```
 * Running on http://0.0.0.0:5000
 * Debug mode: on
```

### Step 3: Open in Browser
Navigate to: **http://localhost:5000**

You should see the Kronos TradingView interface with:
- Candlestick chart
- Prediction panel
- Control parameters
- Watchlist sidebar

---

## 📊 Interface Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    KRONOS TRADINGVIEW                        │
├──────────┬──────────────────────────────────────────────────┤
│ Watchlist│  Header (Symbol, Price, Stats)                  │
│  BTC     │  ┌─────────────────────────────────────────┐   │
│  ETH     │  │                                         │   │
│  BNB     │  │         CANDLESTICK CHART               │   │
│  XRP     │  │                                         │   │
│  SOL     │  │   (Real-time updates)                   │   │
│          │  └─────────────────────────────────────────┘   │
├──────────┼──────────────────────────────────────────────────┤
│ Search   │  Control Panel (Lookback, Pred Len, Temp, Model)│
├──────────┼──────────────────────────────────────────────────┤
│ Settings │  Prediction Panel (Next Period, Price Range, Vol)│
└──────────┴──────────────────────────────────────────────────┘
```

---

## 🎮 How to Use

### Load a Symbol
1. **Option A**: Click a symbol in the watchlist (BTC, ETH, etc.)
2. **Option B**: Type symbol in search box and press Enter

### Change Timeframe
Click buttons: **1M | 5M | 15M | 1H | 4H | 1D | 1W**

### Adjust Prediction Parameters

| Parameter | Range | Description |
|-----------|-------|-------------|
| Lookback Period | 50-500 | Historical candles for context |
| Prediction Length | 10-200 | How many candles to predict |
| Temperature | 0.1-2.0 | Randomness (0.1=deterministic, 2.0=random) |
| Model | Mini/Small/Base | Kronos model size |

### View Predictions
The bottom panel shows:
- **Trend**: Bullish/Bearish sentiment
- **Price Range**: High/Low forecast
- **Volume**: Expected trading volume
- **Confidence**: Model confidence level

---

## 🔌 API Endpoints

### Health Check
```bash
curl http://localhost:5000/health
```

### Get Predictions
```bash
curl -X POST http://localhost:5000/api/predict \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC/USDT",
    "timeframe": "4h",
    "lookback": 200,
    "pred_len": 50,
    "temperature": 1.0,
    "model": "kronos-small"
  }'
```

### Get Portfolio
```bash
curl http://localhost:5000/api/portfolio
```

### Run Backtest
```bash
curl -X POST http://localhost:5000/api/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC/USDT",
    "start_capital": 10000,
    "strategy": "kronos_signals"
  }'
```

---

## 🎨 Customization

### Change Chart Colors
Edit `static/tradingview.html`:
```css
:root {
    --primary: #1e1e1e;      /* Dark background */
    --accent: #4a9eff;       /* Bright blue highlights */
    --success: #26a69a;      /* Green (bullish) */
    --danger: #ef5350;       /* Red (bearish) */
}
```

### Add Custom Symbols
Edit `app_tradingview.py`:
```python
SAMPLE_DATA = {
    'YOUR_SYMBOL': {
        'prices': [100, 101, 102],
        'volatility': 0.02,
        'trend': 'uptrend'
    }
}
```

### Change Update Frequency
Edit `static/tradingview.html`:
```javascript
// Auto-update every 5 seconds
setInterval(updateChart, 5000);  // Change 5000 to desired milliseconds
```

---

## 🐛 Troubleshooting

### Chart Not Loading
**Problem**: White/blank chart area
**Solution**:
1. Check browser console: `F12` → Console tab
2. Look for JavaScript errors
3. Verify API is responding: `curl http://localhost:5000/health`

### Predictions Not Showing
**Problem**: Empty prediction panel
**Solution**:
1. Check server logs for errors
2. Verify model is loaded: `curl http://localhost:5000/health` → `"model_available": true`
3. Try different symbol or timeframe
4. Reduce lookback period

### Server Won't Start
**Problem**: `Port 5000 already in use`
**Solution**:
```bash
# Use different port
python app_tradingview.py --port 8000
```

Or kill existing process:
```bash
lsof -i :5000  # Find process
kill -9 <PID>  # Kill it
```

### Model Download Fails
**Problem**: `Connection error downloading model`
**Solution**:
```bash
# Pre-download models
huggingface-cli download NeoQuasar/Kronos-small
huggingface-cli download NeoQuasar/Kronos-Tokenizer-base
```

---

## 📈 Example Workflow

### 1. Load Historical Data
```python
import pandas as pd
df = pd.read_csv('data.csv')
df['timestamps'] = pd.to_datetime(df['timestamps'])
```

### 2. Get Predictions
```python
import requests

response = requests.post('http://localhost:5000/api/predict', json={
    'symbol': 'BTC/USDT',
    'lookback': 200,
    'pred_len': 50
})

predictions = response.json()['data']['predictions']
print(predictions[0])  # First prediction
```

### 3. Backtest Strategy
```python
response = requests.post('http://localhost:5000/api/backtest', json={
    'symbol': 'BTC/USDT',
    'start_capital': 10000
})

metrics = response.json()['metrics']
print(f"Win Rate: {metrics['win_rate']}%")
print(f"Total P&L: ${metrics['total_pnl']}")
```

---

## 🚀 Advanced Features

### Multi-Symbol Dashboard
```javascript
// Monitor multiple symbols simultaneously
const symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'];
symbols.forEach(symbol => {
    loadSymbol(symbol);
});
```

### Portfolio Tracking
```javascript
// Get portfolio status
fetch('/api/portfolio')
    .then(r => r.json())
    .then(data => console.log(data.portfolio));
```

### Technical Indicators
```javascript
// Calculate indicators
fetch('/api/indicators', {
    method: 'POST',
    body: JSON.stringify({
        prices: [100, 101, 102, 103],
        indicators: ['MA', 'RSI', 'MACD']
    })
})
```

---

## 🔗 Integration Examples

### Using with Real Data (yfinance)
```python
import yfinance as yf

def get_real_data():
    df = yf.download('BTC-USD', period='1y', interval='4h')
    return df
```

### Using with Crypto Data (ccxt)
```python
import ccxt

exchange = ccxt.binance()
ohlcv = exchange.fetch_ohlcv('BTC/USDT', '4h', limit=200)
```

### Using with Equity Data
```python
import pandas_datareader as pdr

df = pdr.get_data_yahoo('AAPL', start='2024-01-01')
```

---

## 📊 Performance Benchmarks

| Model | Prediction Speed | Memory | Accuracy |
|-------|-----------------|--------|----------|
| Kronos-mini | ~50ms | 500MB | Good |
| Kronos-small | ~200ms | 2GB | Very Good |
| Kronos-base | ~1000ms | 8GB | Excellent |

---

## 🎓 Learning Resources

- **Kronos Paper**: https://arxiv.org/abs/2508.02739
- **TradingView Docs**: https://tradingview.com/lightweight-charts/
- **Flask Documentation**: https://flask.palletsprojects.com/
- **Pandas Guide**: https://pandas.pydata.org/docs/

---

## 💡 Tips & Tricks

### Pro Tips
1. **Use smaller lookback for speed**: 100-150 candles is faster than 500
2. **Batch predictions**: Predict multiple symbols at once
3. **Cache results**: Reuse predictions within same period
4. **Monitor confidence**: High confidence predictions are more reliable

### Common Mistakes
1. ❌ Using too large lookback (slows down)
2. ❌ Ignoring prediction confidence
3. ❌ Not validating predictions on historical data
4. ❌ Over-trading on signals

---

## 📞 Support

Having issues? Check:
1. **Server logs**: Look for error messages in console
2. **Browser console**: `F12` → Console tab
3. **API status**: `curl http://localhost:5000/health`
4. **GitHub Issues**: https://github.com/shiyu-coder/Kronos/issues

---

## 🎉 Next Steps

1. ✅ Load different symbols and timeframes
2. ✅ Try all Kronos models (mini, small, base)
3. ✅ Run backtests on historical data
4. ✅ Customize chart colors and settings
5. ✅ Integrate with real market data
6. ✅ Build automated trading strategies

Happy trading! 🚀

---

*Last Updated: 2024*
*Kronos © MIT License*
