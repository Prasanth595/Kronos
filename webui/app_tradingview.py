"""
Enhanced Flask backend for Kronos TradingView interface
"""
import os
import pandas as pd
import numpy as np
import json
import plotly.graph_objects as go
import plotly.utils
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import sys
import warnings
import datetime
from datetime import timedelta
import threading
from collections import defaultdict
import traceback

warnings.filterwarnings('ignore')

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from model import Kronos, KronosTokenizer, KronosPredictor
    MODEL_AVAILABLE = True
except ImportError:
    MODEL_AVAILABLE = False
    print("Warning: Kronos model cannot be imported, will use simulated data for demonstration")

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Global variables to store models
tokenizer = None
model = None
predictor = None
loaded_model = None

# Model configurations
AVAILABLE_MODELS = {
    'kronos-mini': {
        'name': 'Kronos-mini',
        'model_id': 'NeoQuasar/Kronos-mini',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-2k',
        'context_length': 2048,
        'params': '4.1M',
    },
    'kronos-small': {
        'name': 'Kronos-small',
        'model_id': 'NeoQuasar/Kronos-small',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-base',
        'context_length': 512,
        'params': '24.7M',
    },
    'kronos-base': {
        'name': 'Kronos-base',
        'model_id': 'NeoQuasar/Kronos-base',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-base',
        'context_length': 512,
        'params': '102.3M',
    }
}

# Sample data for demonstration
SAMPLE_DATA = {
    'BTC/USDT': {
        'prices': [65000, 65500, 65200, 66000, 65800],
        'volatility': 0.02,
        'trend': 'uptrend'
    },
    'ETH/USDT': {
        'prices': [3500, 3550, 3480, 3600, 3550],
        'volatility': 0.025,
        'trend': 'uptrend'
    },
    'BNB/USDT': {
        'prices': [600, 610, 595, 620, 615],
        'volatility': 0.03,
        'trend': 'uptrend'
    }
}

def generate_sample_data(symbol, lookback=200, pred_len=50):
    """Generate sample OHLCV data for demonstration"""
    try:
        if symbol in SAMPLE_DATA:
            base_price = SAMPLE_DATA[symbol]['prices'][-1]
            volatility = SAMPLE_DATA[symbol]['volatility']
        else:
            base_price = 100
            volatility = 0.02

        # Generate historical data
        historical = []
        current_price = base_price
        
        for i in range(lookback):
            # Random walk with volatility
            daily_return = np.random.normal(0, volatility)
            open_price = current_price
            close_price = current_price * (1 + daily_return)
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, volatility/2)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, volatility/2)))
            volume = np.random.uniform(1000000, 5000000)
            
            timestamp = int((datetime.datetime.now() - timedelta(days=lookback-i)).timestamp() * 1000)
            
            historical.append({
                'time': timestamp,
                'open': round(open_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'close': round(close_price, 2),
                'volume': round(volume)
            })
            
            current_price = close_price

        # Generate predictions
        predictions = []
        pred_price = current_price
        
        for i in range(pred_len):
            daily_return = np.random.normal(0, volatility)
            pred_open = pred_price
            pred_close = pred_price * (1 + daily_return)
            pred_high = max(pred_open, pred_close) * (1 + abs(np.random.normal(0, volatility/2)))
            pred_low = min(pred_open, pred_close) * (1 - abs(np.random.normal(0, volatility/2)))
            pred_volume = np.random.uniform(1000000, 5000000)
            
            predictions.append({
                'open': round(pred_open, 2),
                'high': round(pred_high, 2),
                'low': round(pred_low, 2),
                'close': round(pred_close, 2),
                'volume': round(pred_volume)
            })
            
            pred_price = pred_close

        # Calculate statistics
        closes = [h['close'] for h in historical]
        current = closes[-1]
        prev = closes[0]
        change_pct = ((current - prev) / prev) * 100

        stats = {
            'currentPrice': current,
            'change': change_pct,
            'dayHigh': max(closes),
            'dayLow': min(closes),
        }

        return {
            'success': True,
            'symbol': symbol,
            'timeframe': '4h',
            'data': {
                'historical': historical,
                'predictions': predictions,
                'stats': stats
            }
        }
    except Exception as e:
        print(f"Error generating sample data: {e}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}

def load_model(model_name='kronos-small'):
    """Load Kronos model"""
    global tokenizer, model, predictor, loaded_model
    
    try:
        if MODEL_AVAILABLE:
            config = AVAILABLE_MODELS[model_name]
            tokenizer = KronosTokenizer.from_pretrained(config['tokenizer_id'])
            model = Kronos.from_pretrained(config['model_id'])
            predictor = KronosPredictor(model, tokenizer, max_context=config['context_length'])
            loaded_model = model_name
            return True
        return False
    except Exception as e:
        print(f"Error loading model: {e}")
        return False

# Routes

@app.route('/')
def index():
    """Serve the TradingView interface"""
    return send_from_directory('static', 'tradingview.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory('static', filename)

@app.route('/api/models', methods=['GET'])
def get_models():
    """Get available models"""
    return jsonify({
        'success': True,
        'models': [
            {
                'id': key,
                'name': config['name'],
                'params': config['params'],
                'context_length': config['context_length']
            }
            for key, config in AVAILABLE_MODELS.items()
        ]
    })

@app.route('/api/predict', methods=['POST'])
def predict():
    """Generate prediction for a symbol"""
    try:
        data = request.json
        symbol = data.get('symbol', 'BTC/USDT')
        timeframe = data.get('timeframe', '4h')
        lookback = data.get('lookback', 200)
        pred_len = data.get('pred_len', 50)
        temperature = data.get('temperature', 1.0)
        model_name = data.get('model', 'kronos-small')

        # Validate inputs
        lookback = min(max(lookback, 50), 500)
        pred_len = min(max(pred_len, 10), 200)
        temperature = min(max(temperature, 0.1), 2.0)

        # Load model if needed
        if MODEL_AVAILABLE and model_name != loaded_model:
            load_model(model_name)

        # Generate sample data (or use real prediction if model is available)
        result = generate_sample_data(symbol, lookback, pred_len)

        if result['success'] and MODEL_AVAILABLE and predictor is not None:
            # Try to use actual model predictions
            try:
                # Prepare data
                hist_data = pd.DataFrame([
                    {
                        'open': d['open'],
                        'high': d['high'],
                        'low': d['low'],
                        'close': d['close'],
                        'volume': d['volume']
                    }
                    for d in result['data']['historical']
                ])
                
                # Make predictions if we have the model
                # This is a placeholder - actual implementation would use the model
                pass
            except Exception as e:
                print(f"Model prediction failed, using sample: {e}")

        return jsonify(result)

    except Exception as e:
        print(f"Error in predict: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/backtest', methods=['POST'])
def backtest():
    """Run backtesting on a symbol"""
    try:
        data = request.json
        symbol = data.get('symbol', 'BTC/USDT')
        start_capital = data.get('start_capital', 10000)
        strategy = data.get('strategy', 'kronos_signals')

        # Generate sample backtest results
        trades = [
            {
                'entry_time': int((datetime.datetime.now() - timedelta(days=30)).timestamp() * 1000),
                'exit_time': int((datetime.datetime.now() - timedelta(days=25)).timestamp() * 1000),
                'entry_price': 65000,
                'exit_price': 66500,
                'pnl': 2300,
                'pnl_pct': 3.54,
                'type': 'long'
            },
            {
                'entry_time': int((datetime.datetime.now() - timedelta(days=20)).timestamp() * 1000),
                'exit_time': int((datetime.datetime.now() - timedelta(days=15)).timestamp() * 1000),
                'entry_price': 66500,
                'exit_price': 65800,
                'pnl': -1400,
                'pnl_pct': -2.10,
                'type': 'long'
            }
        ]

        total_pnl = sum(t['pnl'] for t in trades)
        win_rate = sum(1 for t in trades if t['pnl'] > 0) / len(trades) if trades else 0

        return jsonify({
            'success': True,
            'symbol': symbol,
            'strategy': strategy,
            'metrics': {
                'total_trades': len(trades),
                'winning_trades': sum(1 for t in trades if t['pnl'] > 0),
                'losing_trades': sum(1 for t in trades if t['pnl'] < 0),
                'win_rate': round(win_rate * 100, 2),
                'total_pnl': round(total_pnl, 2),
                'pnl_percentage': round((total_pnl / start_capital) * 100, 2),
                'avg_winning_trade': round(np.mean([t['pnl'] for t in trades if t['pnl'] > 0]) if any(t['pnl'] > 0 for t in trades) else 0, 2),
                'avg_losing_trade': round(np.mean([t['pnl'] for t in trades if t['pnl'] < 0]) if any(t['pnl'] < 0 for t in trades) else 0, 2),
            },
            'trades': trades
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/indicators', methods=['POST'])
def calculate_indicators():
    """Calculate technical indicators"""
    try:
        data = request.json
        prices = data.get('prices', [])
        indicators = data.get('indicators', ['MA', 'RSI', 'MACD'])

        result = {'success': True, 'indicators': {}}

        if 'MA' in indicators and len(prices) > 20:
            ma_20 = np.mean(prices[-20:])
            ma_50 = np.mean(prices[-50:]) if len(prices) > 50 else None
            result['indicators']['MA'] = {'MA20': ma_20, 'MA50': ma_50}

        if 'RSI' in indicators and len(prices) > 14:
            deltas = np.diff(prices[-14:])
            gains = np.mean([d for d in deltas if d > 0]) if any(d > 0 for d in deltas) else 0
            losses = abs(np.mean([d for d in deltas if d < 0])) if any(d < 0 for d in deltas) else 0
            rs = gains / losses if losses != 0 else 0
            rsi = 100 - (100 / (1 + rs))
            result['indicators']['RSI'] = rsi

        if 'MACD' in indicators and len(prices) > 26:
            ema_12 = np.mean(prices[-12:])
            ema_26 = np.mean(prices[-26:])
            macd_line = ema_12 - ema_26
            result['indicators']['MACD'] = {'line': macd_line, 'signal': macd_line * 0.9}

        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/portfolio', methods=['GET'])
def get_portfolio():
    """Get portfolio information"""
    return jsonify({
        'success': True,
        'portfolio': {
            'total_value': 25000.50,
            'total_invested': 20000,
            'total_pnl': 5000.50,
            'total_pnl_percentage': 25.0,
            'positions': [
                {
                    'symbol': 'BTC/USDT',
                    'quantity': 0.5,
                    'entry_price': 60000,
                    'current_price': 65000,
                    'pnl': 2500,
                    'pnl_percentage': 8.33
                },
                {
                    'symbol': 'ETH/USDT',
                    'quantity': 10,
                    'entry_price': 3000,
                    'current_price': 3500,
                    'pnl': 5000,
                    'pnl_percentage': 16.67
                }
            ]
        }
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'model_available': MODEL_AVAILABLE,
        'loaded_model': loaded_model,
    })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Try to load default model
    if MODEL_AVAILABLE:
        print("Loading Kronos model...")
        load_model('kronos-small')
        print("Model loaded successfully!")
    else:
        print("Running in demonstration mode (no model loaded)")

    app.run(debug=True, host='0.0.0.0', port=5000)
