# Kronos TradingView Interface

A professional, real-time TradingView-like interface built for the Kronos financial prediction model. This interface provides advanced charting, technical analysis, portfolio management, and AI-powered price predictions.

## Features

### 📊 Real-Time Charts
- **Lightweight Charts Integration**: Professional candlestick charts with TradingView quality
- **Multiple Timeframes**: 1M, 5M, 15M, 1H, 4H, 1D, 1W support
- **Interactive Zooming & Panning**: Intuitive chart navigation
- **Real-time Updates**: Auto-refresh every 5 seconds

### 🤖 Kronos AI Integration
- **Model Selection**: Choose between Kronos-mini, Kronos-small, and Kronos-base
- **Prediction Overlay**: Display AI forecasts directly on charts
- **Confidence Intervals**: Visualize prediction uncertainty
- **Configurable Parameters**:
  - Lookback Period (50-500 candles)
  - Prediction Length (10-200 candles)
  - Temperature/Sampling Control (0.1-2.0)

### 📈 Technical Analysis
- **Multiple Indicators**:
  - Moving Averages (MA20, MA50)
  - Relative Strength Index (RSI)
  - MACD (Moving Average Convergence Divergence)
  - Bollinger Bands
  - Volume Analysis

### 💼 Portfolio Management
- **Position Tracking**: Monitor current holdings
- **P&L Calculations**: Real-time profit/loss tracking
- **Portfolio Stats**: Total value, allocation, performance

### 🔄 Backtesting
- **Historical Simulation**: Test strategies on past data
- **Performance Metrics**:
  - Win rate
  - Total P&L
  - Sharpe ratio
  - Maximum drawdown
  - Average trade statistics

### 🎨 Professional UI/UX
- **Dark Theme**: Eye-friendly professional design
- **Responsive Layout**: Works on desktop and tablets
- **Watchlist**: Track favorite symbols
- **Symbol Search**: Quick symbol lookup
- **Real-time Stats**: Current price, change%, high/low

## Installation

### Prerequisites
- Python 3.8+
- pip or conda

### Setup

1. **Install dependencies**:
```bash
pip install -r webui/requirements.txt
```

2. **Run the Flask server**:
```bash
python webui/app_tradingview.py
```

3. **Access the interface**:
Open your browser to `http://localhost:5000`

## Usage

### Basic Workflow

1. **Select a Symbol**:
   - Click on watchlist items (BTC/USDT, ETH/USDT, etc.)
   - Or search for a symbol in the search bar

2. **Choose Timeframe**:
   - Click timeframe buttons: 1M, 5M, 15M, 1H, 4H, 1D, 1W

3. **Adjust Parameters**:
   - **Lookback Period**: Historical data used for prediction (50-500 candles)
   - **Prediction Length**: How many candles to predict (10-200)
   - **Temperature**: Control sampling randomness (0.1=deterministic, 2.0=random)
   - **Model**: Select which Kronos model to use

4. **View Predictions**:
   - AI predictions appear in the prediction panel
   - Shows expected price range (high/low)
   - Displays confidence metrics
   - Volume forecasts

### API Reference

#### GET `/api/models`
Get available Kronos models
```json
{
  "success": true,
  "models": [
    {
      "id": "kronos-mini",
      "name": "Kronos-mini",
      "params": "4.1M",
      "context_length": 2048
    }
  ]
}
```

#### POST `/api/predict`
Generate price predictions
```json
{
  "symbol": "BTC/USDT",
  "timeframe": "4h",
  "lookback": 200,
  "pred_len": 50,
  "temperature": 1.0,
  "model": "kronos-small"
}
```

Response:
```json
{
  "success": true,
  "symbol": "BTC/USDT",
  "data": {
    "historical": [...],
    "predictions": [...],
    "stats": {
      "currentPrice": 65000,
      "change": 2.5,
      "dayHigh": 66000,
      "dayLow": 64000
    }
  }
}
```

#### POST `/api/backtest`
Run backtesting analysis
```json
{
  "symbol": "BTC/USDT",
  "start_capital": 10000,
  "strategy": "kronos_signals"
}
```

#### POST `/api/indicators`
Calculate technical indicators
```json
{
  "prices": [100, 101, 102, ...],
  "indicators": ["MA", "RSI", "MACD"]
}
```

#### GET `/api/portfolio`
Get portfolio information
```json
{
  "success": true,
  "portfolio": {
    "total_value": 25000.50,
    "total_pnl": 5000.50,
    "positions": [...]
  }
}
```

#### GET `/health`
Health check
```json
{
  "status": "healthy",
  "model_available": true,
  "loaded_model": "kronos-small"
}
```

## Configuration

### Flask Server Options

Edit `app_tradingview.py` to customize:

```python
# Change port
app.run(debug=True, host='0.0.0.0', port=8000)

# Change CORS settings
CORS(app, resources={r"/api/*": {"origins": "*"}})
```

### Chart Settings

Modify chart appearance in `static/tradingview.html`:

```javascript
// Chart colors
--primary: #1e1e1e;
--accent: #4a9eff;
--success: #26a69a;
--danger: #ef5350;
```

## Advanced Features

### Multi-Symbol Monitoring
```javascript
// Add custom watchlist
const watchlist = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'YOUR_SYMBOL'];
```

### Custom Indicators
Add new technical indicators to the analysis panel:
```python
@app.route('/api/indicators/custom', methods=['POST'])
def custom_indicator():
    # Implement your custom indicator logic
    pass
```

### WebSocket Real-time Updates (Future)
Replace AJAX polling with WebSocket for true real-time updates:
```javascript
const ws = new WebSocket('ws://localhost:5000/stream');
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    updateChart(data);
};
```

## Model Information

### Kronos-mini
- **Parameters**: 4.1M
- **Context**: 2048 tokens
- **Speed**: Fastest
- **Use Case**: Real-time updates, resource-constrained

### Kronos-small
- **Parameters**: 24.7M
- **Context**: 512 tokens
- **Speed**: Balanced
- **Use Case**: Default choice, good accuracy/speed trade-off

### Kronos-base
- **Parameters**: 102.3M
- **Context**: 512 tokens
- **Speed**: Slower
- **Use Case**: Highest accuracy, best predictions

## Performance Tips

1. **Reduce Lookback for Speed**: Smaller lookback window = faster predictions
2. **Use Mini Model for Real-time**: Kronos-mini is much faster
3. **Batch Operations**: Predict multiple symbols together
4. **Cache Data**: Reuse historical data when possible

## Troubleshooting

### Model Not Loading
```
Check: python webui/app_tradingview.py
```

If models fail to download:
```bash
# Manually cache models
huggingface-cli download NeoQuasar/Kronos-small
huggingface-cli download NeoQuasar/Kronos-Tokenizer-base
```

### Slow Predictions
- Use smaller model (kronos-mini)
- Reduce lookback period
- Increase prediction intervals

### Chart Not Showing
- Check browser console for JavaScript errors
- Verify API endpoints are responding: `curl http://localhost:5000/health`
- Clear browser cache

## Integration with Data Sources

### Add Live Price Data
```python
import yfinance as yf

def get_live_prices(symbol):
    ticker = yf.Ticker(symbol)
    return ticker.history(period='1y')
```

### Add Cryptocurrency Data
```python
import ccxt

exchange = ccxt.binance()
ohlcv = exchange.fetch_ohlcv('BTC/USDT', '4h')
```

### Add Equity Data
```python
import pandas_datareader as pdr

df = pdr.get_data_yahoo('AAPL', start='2024-01-01')
```

## Keyboard Shortcuts

- **Enter** (in search): Load symbol
- **← →**: Navigate timeframes (future)
- **+/-**: Zoom in/out (future)

## Browser Compatibility

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (responsive design)

## License

This interface is part of the Kronos project, licensed under the MIT License.

## Support & Feedback

For issues, feature requests, or questions:
- GitHub Issues: [shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos)
- Documentation: [Kronos Docs](https://github.com/shiyu-coder/Kronos)

## Resources

- **Kronos Paper**: https://arxiv.org/abs/2508.02739
- **Hugging Face Models**: https://huggingface.co/NeoQuasar
- **Live Demo**: https://shiyu-coder.github.io/Kronos-demo/
- **TradingView Lightweight Charts**: https://tradingview.com/lightweight-charts/
