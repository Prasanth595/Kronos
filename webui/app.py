import os
import pandas as pd
import numpy as np
import json
import plotly.graph_objects as go
import plotly.utils
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sys
import warnings
import datetime
warnings.filterwarnings('ignore')

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from model import Kronos, KronosTokenizer, KronosPredictor
    MODEL_AVAILABLE = True
except ImportError:
    MODEL_AVAILABLE = False
    print("Warning: Kronos model cannot be imported, will use simulated data for demonstration")

app = Flask(__name__)
CORS(app)

# Global variables to store models
tokenizer = None
model = None
predictor = None

# Available model configurations
AVAILABLE_MODELS = {
    'kronos-mini': {
        'name': 'Kronos-mini',
        'model_id': 'NeoQuasar/Kronos-mini',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-2k',
        'context_length': 2048,
        'params': '4.1M',
        'description': 'Lightweight model, suitable for fast prediction'
    },
    'kronos-small': {
        'name': 'Kronos-small',
        'model_id': 'NeoQuasar/Kronos-small',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-base',
        'context_length': 512,
        'params': '24.7M',
        'description': 'Small model, balanced performance and speed'
    },
    'kronos-base': {
        'name': 'Kronos-base',
        'model_id': 'NeoQuasar/Kronos-base',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-base',
        'context_length': 512,
        'params': '102.3M',
        'description': 'Base model, provides better prediction quality'
    }
}

def load_data_files():
    """Scan data directory and return available data files"""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    data_files = []
    
    if os.path.exists(data_dir):
        for file in os.listdir(data_dir):
            if file.endswith(('.csv', '.feather')):
                file_path = os.path.join(data_dir, file)
                file_size = os.path.getsize(file_path)
                data_files.append({
                    'name': file,
                    'path': file_path,
                    'size': f"{file_size / 1024:.1f} KB" if file_size < 1024*1024 else f"{file_size / (1024*1024):.1f} MB"
                })
    
    return data_files

def load_data_file(file_path: str) -> tuple[pd.DataFrame | None, str | None]:
    """Load data file"""
    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif file_path.endswith('.feather'):
            df = pd.read_feather(file_path)
        else:
            return None, "Unsupported file format"
        
        # Check required columns
        required_cols = ['open', 'high', 'low', 'close']
        if not all(col in df.columns for col in required_cols):
            return None, f"Missing required columns: {required_cols}"
        
        # Process timestamp column
        if 'timestamps' in df.columns:
            df['timestamps'] = pd.to_datetime(df['timestamps'])
        elif 'timestamp' in df.columns:
            df['timestamps'] = pd.to_datetime(df['timestamp'])
        elif 'date' in df.columns:
            # If column name is 'date', rename it to 'timestamps'
            df['timestamps'] = pd.to_datetime(df['date'])
        else:
            # If no timestamp column exists, create one
            df['timestamps'] = pd.date_range(start='2024-01-01', periods=len(df), freq='1H')
        
        # Ensure numeric columns are numeric type
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Process volume column (optional)
        if 'volume' in df.columns:
            df['volume'] = pd.to_numeric(df[col], errors='coerce')
        
        # Process amount column (optional, but not used for prediction)
        if 'amount' in df.columns:
            df['amount'] = pd.to_numeric(df[col], errors='coerce')
        
        # Remove rows containing NaN values
        df = df.dropna()
        
        # New log message for data freshness debugging
        if 'timestamps' in df.columns and not df.empty:
            print(f"Loaded data from {file_path}. Rows: {len(df)}. Time range: {df['timestamps'].min().isoformat()} to {df['timestamps'].max().isoformat()}.")
        elif not df.empty:
            print(f"Loaded data from {file_path}. Rows: {len(df)}. No timestamp column found.")
        else:
            print(f"Loaded data from {file_path}. No data found after processing.")

        return df, None
        
    except Exception as e:
        print(f"Failed to load file: {file_path} - {e}") # Added file_path to error log
        return None, f"Failed to load file: {str(e)}"

def save_prediction_results(file_path, prediction_type, prediction_results, actual_data, input_data, prediction_params):
    """Save prediction results to file"""
    try:
        # Create prediction results directory
        results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prediction_results')
        os.makedirs(results_dir, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'prediction_{timestamp}.json'
        filepath = os.path.join(results_dir, filename)
        
        # Prepare data for saving
        save_data = {
            'timestamp': datetime.datetime.now().isoformat(),
            'file_path': file_path,
            'prediction_type': prediction_type,
            'prediction_params': prediction_params,
            'input_data_summary': {
                'rows': len(input_data),
                'columns': list(input_data.columns),
                'price_range': {
                    'open': {'min': float(input_data['open'].min()), 'max': float(input_data['open'].max())},
                    'high': {'min': float(input_data['high'].min()), 'max': float(input_data['high'].max())},
                    'low': {'min': float(input_data['low'].min()), 'max': float(input_data['low'].max())},
                    'close': {'min': float(input_data['close'].min()), 'max': float(input_data['close'].max())}
                },
                'last_values': {
                    'open': float(input_data['open'].iloc[-1]),
                    'high': float(input_data['high'].iloc[-1]),
                    'low': float(input_data['low'].iloc[-1]),
                    'close': float(input_data['close'].iloc[-1])
                }
            },
            'prediction_results': prediction_results,
            'actual_data': actual_data,
            'analysis': {}
        }
        
        # If actual data exists, perform comparison analysis
        if actual_data and len(actual_data) > 0 and len(prediction_results) > 0: # Ensure prediction results also exist
            # Calculate continuity analysis
            last_pred = prediction_results[0]  # First prediction point
            first_actual = actual_data[0]      # First actual point
                
            save_data['analysis']['continuity'] = {
                    'last_prediction': {
                        'open': last_pred['open'],
                        'high': last_pred['high'],
                        'low': last_pred['low'],
                        'close': last_pred['close']
                    },
                    'first_actual': {
                        'open': first_actual['open'],
                        'high': first_actual['high'],
                        'low': first_actual['low'],
                        'close': first_actual['close']
                    },
                    'gaps': {
                        'open_gap': abs(last_pred['open'] - first_actual['open']),
                        'high_gap': abs(last_pred['high'] - first_actual['high']),
                        'low_gap': abs(last_pred['low'] - first_actual['low']),
                        'close_gap': abs(last_pred['close'] - first_actual['close'])
                    },
                    'gap_percentages': {
                        'open_gap_pct': (abs(last_pred['open'] - first_actual['open']) / first_actual['open']) * 100 if first_actual['open'] != 0 else float('inf'),
                        'high_gap_pct': (abs(last_pred['high'] - first_actual['high']) / first_actual['high']) * 100 if first_actual['high'] != 0 else float('inf'),
                        'low_gap_pct': (abs(last_pred['low'] - first_actual['low']) / first_actual['low']) * 100 if first_actual['low'] != 0 else float('inf'),
                        'close_gap_pct': (abs(last_pred['close'] - first_actual['close']) / first_actual['close']) * 100 if first_actual['close'] != 0 else float('inf')
                    }
                }
        
        # Save to file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        
        print(f"Prediction results saved to: {filepath}")
        return filepath
        
    except Exception as e:
        print(f"Failed to save prediction results: {e}")
        return None

def create_prediction_chart(df: pd.DataFrame, pred_df: pd.DataFrame | None, lookback: int, pred_len: int, actual_df: pd.DataFrame | None = None, historical_start_idx: int = 0) -> str:
    """Create prediction chart"""
    # Use specified historical data start position, not always from the beginning of df
    if historical_start_idx + lookback + pred_len <= len(df):
        # Display lookback historical points + pred_len prediction points starting from specified position
        historical_df = df.iloc[historical_start_idx:historical_start_idx+lookback]
    else:
        # If data is insufficient, adjust to maximum available range
        available_lookback = min(lookback, len(df) - historical_start_idx)
        historical_df = df.iloc[historical_start_idx:historical_start_idx+available_lookback]
    
    # Create chart
    fig = go.Figure()
    
    # Add historical data (candlestick chart)
    fig.add_trace(go.Candlestick(
        x=historical_df['timestamps'] if 'timestamps' in historical_df.columns else historical_df.index,
        open=historical_df['open'],
        high=historical_df['high'],
        low=historical_df['low'],
        close=historical_df['close'],
        name=f'Historical Data ({len(historical_df)} data points)', # Make count dynamic
        increasing_line_color='#26A69A',
        decreasing_line_color='#EF5350'
    ))
    
    # Add prediction data (candlestick chart)
    pred_timestamps = pd.Series(dtype='datetime64[ns]') # Initialize for consistent type inference
    if pred_df is not None and not pred_df.empty:
        # Calculate prediction data timestamps - ensure continuity with historical data
        if 'timestamps' in df.columns and not historical_df.empty:
            # Start from the last timestamp of historical data, create prediction timestamps with the same time interval
            last_timestamp = historical_df['timestamps'].iloc[-1]
            time_diff = df['timestamps'].iloc[1] - df['timestamps'].iloc[0] if len(df) > 1 else pd.Timedelta(hours=1)
            
            pred_timestamps = pd.date_range(
                start=last_timestamp + time_diff,
                periods=len(pred_df),
                freq=time_diff
            )
        else:
            # If no timestamps, use index
            pred_timestamps = pd.Series(range(len(historical_df), len(historical_df) + len(pred_df))) # Use Series for consistency
        
        fig.add_trace(go.Candlestick(
            x=pred_timestamps,
            open=pred_df['open'],
            high=pred_df['high'],
            low=pred_df['low'],
            close=pred_df['close'],
            name=f'Prediction Data ({len(pred_df)} data points)', # Make count dynamic
            increasing_line_color='#66BB6A',
            decreasing_line_color='#FF7043'
        ))
    
    # Add actual data for comparison (if exists)
    actual_timestamps = pd.Series(dtype='datetime64[ns]') # Initialize for consistent type inference
    if actual_df is not None and not actual_df.empty:
        # Actual data should be in the same time period as prediction data
        if 'timestamps' in df.columns:
            if not pred_timestamps.empty:
                actual_timestamps = pred_timestamps # Align with prediction timestamps if they were generated
            elif not historical_df.empty:
                last_timestamp = historical_df['timestamps'].iloc[-1]
                time_diff = df['timestamps'].iloc[1] - df['timestamps'].iloc[0] if len(df) > 1 else pd.Timedelta(hours=1)
                actual_timestamps = pd.date_range(
                    start=last_timestamp + time_diff,
                    periods=len(actual_df),
                    freq=time_diff
                )
        if actual_timestamps.empty:
            actual_timestamps = pd.Series(range(len(historical_df), len(historical_df) + len(actual_df))) # Fallback to index Series
        
        fig.add_trace(go.Candlestick(
            x=actual_timestamps,
            open=actual_df['open'],
            high=actual_df['high'],
            low=actual_df['low'],
            close=actual_df['close'],
            name=f'Actual Data ({len(actual_df)} data points)', # Make count dynamic
            increasing_line_color='#FF9800',
            decreasing_line_color='#F44336'
        ))
    
    # Update layout
    fig.update_layout(
        title=f'Kronos Financial Prediction Results - {len(historical_df)} Historical Points + {len(pred_df) if pred_df is not None else 0} Prediction Points' + (f' vs {len(actual_df)} Actual Points' if actual_df is not None and not actual_df.empty else ''), # Dynamic title
        xaxis_title='Time',
        yaxis_title='Price',
        template='plotly_white',
        height=600,
        showlegend=True
    )
    
    # Ensure x-axis time continuity
    # Collect all potential timestamps from historical, prediction, and actual data
    all_timestamps_series = []
    if not historical_df.empty and 'timestamps' in historical_df.columns:
        all_timestamps_series.append(historical_df['timestamps'])
    if not pred_timestamps.empty:
        all_timestamps_series.append(pred_timestamps)
    if not actual_timestamps.empty:
        all_timestamps_series.append(actual_timestamps)
    
    if all_timestamps_series:
        all_timestamps_combined = pd.concat(all_timestamps_series).drop_duplicates().sort_values()
        if not all_timestamps_combined.empty:
            fig.update_xaxes(
                range=[all_timestamps_combined.iloc[0], all_timestamps_combined.iloc[-1]],
                rangeslider_visible=False,
                type='date'
            )
    
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

def get_latest_prediction_file() -> str | None:
    """
    Scans the 'prediction_results' directory and returns the path to the most recent prediction JSON file.
    Assumes filename format 'prediction_YYYYMMDD_HHMMSS.json'.
    Returns None if no prediction files are found or directory does not exist.
    """
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prediction_results')
    if not os.path.exists(results_dir):
        print(f"Warning: Prediction results directory not found at {results_dir}")
        return None

    json_files = [f for f in os.listdir(results_dir) if f.startswith('prediction_') and f.endswith('.json')]
    if not json_files:
        print(f"No prediction JSON files found in {results_dir}")
        return None

    try:
        # Sort files by the timestamp embedded in their names
        json_files.sort(key=lambda x: datetime.datetime.strptime(x, 'prediction_%Y%m%d_%H%M%S.json'), reverse=True)
        latest_file = os.path.join(results_dir, json_files[0])
        print(f"Found latest prediction file: {latest_file}")
        return latest_file
    except ValueError as e:
        print(f"Error parsing prediction filenames for sorting: {e}. Skipping auto-load of latest prediction.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while getting latest prediction file: {e}")
        return None

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

@app.route('/api/data-files')
def get_data_files():
    """Get available data file list"""
    data_files = load_data_files()
    return jsonify(data_files)

@app.route('/api/load-data', methods=['POST'])
def load_data():
    """Load data file"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        
        if not file_path:
            return jsonify({'error': 'File path cannot be empty'}), 400
        
        df, error = load_data_file(file_path)
        if error:
            return jsonify({'error': error}), 400
        
        # Detect data time frequency
        def detect_timeframe(df_local: pd.DataFrame) -> str:
            if len(df_local) < 2:
                return "Unknown"
            
            time_diffs = []
            # Check first 10 time differences or up to df_local length
            for i in range(1, min(10, len(df_local))):  
                diff = df_local['timestamps'].iloc[i] - df_local['timestamps'].iloc[i-1]
                time_diffs.append(diff)
            
            if not time_diffs:
                return "Unknown"
            
            # Calculate average time difference
            avg_diff = sum(time_diffs, pd.Timedelta(0)) / len(time_diffs)
            
            # Convert to readable format
            if avg_diff < pd.Timedelta(minutes=1):
                return f"{avg_diff.total_seconds():.0f} seconds"
            elif avg_diff < pd.Timedelta(hours=1):
                return f"{avg_diff.total_seconds() / 60:.0f} minutes"
            elif avg_diff < pd.Timedelta(days=1):
                return f"{avg_diff.total_seconds() / 3600:.0f} hours"
            else:
                return f"{avg_diff.days} days"
        
        # Return data information
        data_info = {
            'rows': len(df),
            'columns': list(df.columns),
            'start_date': df['timestamps'].min().isoformat() if 'timestamps' in df.columns else 'N/A',
            'end_date': df['timestamps'].max().isoformat() if 'timestamps' in df.columns else 'N/A',
            'price_range': {
                'min': float(df[['open', 'high', 'low', 'close']].min().min()),
                'max': float(df[['open', 'high', 'low', 'close']].max().max())
            },
            'prediction_columns': ['open', 'high', 'low', 'close'] + (['volume'] if 'volume' in df.columns else []),
            'timeframe': detect_timeframe(df)
        }
        
        return jsonify({
            'success': True,
            'data_info': data_info,
            'message': f'Successfully loaded data, total {len(df)} rows'
        })
        
    except Exception as e:
        print(f"Error in /api/load-data: {e}") # Added error log
        return jsonify({'error': f'Failed to load data: {str(e)}'}), 500

@app.route('/api/predict', methods=['POST'])
def predict():
    """Perform prediction"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        lookback = int(data.get('lookback', 400))
        pred_len = int(data.get('pred_len', 120))
        
        # Get prediction quality parameters
        temperature = float(data.get('temperature', 1.0))
        top_p = float(data.get('top_p', 0.9))
        sample_count = int(data.get('sample_count', 1))
        
        if not file_path:
            return jsonify({'error': 'File path cannot be empty'}), 400
        
        # Load data
        df, error = load_data_file(file_path)
        if error:
            return jsonify({'error': error}), 400
        
        if len(df) < lookback:
            return jsonify({'error': f'Insufficient data length, need at least {lookback} rows'}), 400
        
        # New log message for prediction data usage
        if 'timestamps' in df.columns and not df.empty:
            print(f"Preparing prediction for data from {file_path}. Total rows: {len(df)}. Time range: {df['timestamps'].min().isoformat()} to {df['timestamps'].max().isoformat()}")
        else:
            print(f"Preparing prediction for data from {file_path}. Total rows: {len(df)}. No timestamp column found.")

        # Perform prediction
        if MODEL_AVAILABLE and predictor is not None:
            try:
                # Use real Kronos model
                # Only use necessary columns: OHLCV, excluding amount
                required_cols = ['open', 'high', 'low', 'close']
                if 'volume' in df.columns:
                    required_cols.append('volume')
                
                # Process time period selection
                start_date = data.get('start_date')
                
                x_df: pd.DataFrame
                x_timestamp: pd.Series
                y_timestamp: pd.Series
                actual_df: pd.DataFrame
                
                if start_date:
                    # Custom time period - use data within selected window
                    start_dt = pd.to_datetime(start_date)
                    
                    # Find data after start time
                    mask = df['timestamps'] >= start_dt
                    time_range_df = df[mask]
                    
                    # Ensure sufficient data: lookback + pred_len
                    if len(time_range_df) < lookback + pred_len:
                        return jsonify({'error': f'Insufficient data from start time {start_dt.strftime("%Y-%m-%d %H:%M")}, need at least {lookback + pred_len} data points, currently only {len(time_range_df)} available'}), 400
                    
                    # Use first lookback data points within selected window for prediction
                    x_df = time_range_df.iloc[:lookback][required_cols]
                    x_timestamp = time_range_df.iloc[:lookback]['timestamps']
                    
                    # Use last pred_len data points within selected window as actual values for comparison
                    actual_df = time_range_df.iloc[lookback:lookback+pred_len]
                    y_timestamp = actual_df['timestamps'] # For model output alignment
                    
                    # Calculate actual time period length (for description)
                    start_timestamp = time_range_df['timestamps'].iloc[0]
                    end_timestamp = time_range_df['timestamps'].iloc[lookback+pred_len-1]
                    time_span = end_timestamp - start_timestamp
                    
                    prediction_type = f"Kronos model prediction (within selected window: first {lookback} data points for prediction, last {pred_len} data points for comparison, time span: {time_span})"
                else:
                    # Use latest data: slice the last (lookback + pred_len) data points from df
                    # The prediction input (x_df) will be the first 'lookback' points of this slice.
                    # The actual data (actual_df) will be the last 'pred_len' points of this slice.
                    if len(df) < lookback + pred_len:
                        print(f"Warning: Not enough data for latest prediction with comparison. Available: {len(df)}, Required: {lookback+pred_len}. Proceeding with prediction without actual comparison data.")
                        # If not enough data for full lookback + pred_len, just take the last 'lookback' for prediction input.
                        x_df = df.iloc[-lookback:][required_cols]
                        x_timestamp = df.iloc[-lookback:]['timestamps']
                        actual_df = pd.DataFrame() # No actuals for comparison
                        y_timestamp = pd.Series(dtype='datetime64[ns]') # Empty timestamp series for model output alignment
                        prediction_type = "Kronos model prediction (latest available data, no comparison)"
                    else:
                        # Take the last (lookback + pred_len) points for the full window
                        latest_window_df = df.iloc[-(lookback + pred_len):]
                        x_df = latest_window_df.iloc[:lookback][required_cols] # Input for prediction model
                        x_timestamp = latest_window_df.iloc[:lookback]['timestamps'] # Timestamps for input
                        actual_df = latest_window_df.iloc[lookback:] # Actuals for comparison
                        y_timestamp = latest_window_df.iloc[lookback:]['timestamps'] # Timestamps for model output alignment
                        prediction_type = "Kronos model prediction (latest data with comparison)"
                
                # Ensure timestamps are Series format, not DatetimeIndex, to avoid .dt attribute error in Kronos model
                if isinstance(x_timestamp, pd.DatetimeIndex):
                    x_timestamp = pd.Series(x_timestamp, name='timestamps')
                if isinstance(y_timestamp, pd.DatetimeIndex):
                    y_timestamp = pd.Series(y_timestamp, name='timestamps')
                
                # Log input data range before prediction
                if not x_timestamp.empty and 'timestamps' in df.columns:
                    print(f"Kronos prediction input: Using {len(x_df)} data points from {x_timestamp.min().isoformat()} to {x_timestamp.max().isoformat()} for prediction.")
                else:
                    print(f"Kronos prediction input: Using {len(x_df)} data points for prediction (no timestamp info).")

                pred_df = predictor.predict(
                    df=x_df,
                    x_timestamp=x_timestamp,
                    y_timestamp=y_timestamp,
                    pred_len=pred_len,
                    T=temperature,
                    top_p=top_p,
                    sample_count=sample_count
                )
                
            except Exception as e:
                print(f"Kronos model prediction failed: {e}") # Log error for server side
                return jsonify({'error': f'Kronos model prediction failed: {str(e)}'}), 500
        else:
            return jsonify({'error': 'Kronos model not loaded, please load model first'}), 400
        
        # Prepare actual data for comparison (if exists)
        actual_data = []
        if not actual_df.empty:
            for _, row in actual_df.iterrows():
                actual_data.append({
                    'timestamp': row['timestamps'].isoformat(),
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': float(row['volume']) if 'volume' in row else 0.0, # ensure float type for volume/amount
                    'amount': float(row['amount']) if 'amount' in row else 0.0
                })
        
        # Create chart - pass historical data start position
        if start_date:
            # Custom time period: find starting position of historical data in original df
            start_dt = pd.to_datetime(start_date)
            mask = df['timestamps'] >= start_dt
            historical_start_idx = df[mask].index[0] if not df[mask].empty else 0
        else:
            # Latest data: start from the beginning of the `latest_window_df` slice in the original `df`
            # This ensures the chart displays the entire window used for the latest prediction and comparison.
            historical_start_idx = max(0, len(df) - (lookback + pred_len))
        
        chart_json = create_prediction_chart(df, pred_df, lookback, pred_len, actual_df, historical_start_idx)
        
        # Prepare prediction result data - calculate future timestamps
        future_timestamps = pd.Series(dtype='datetime64[ns]') # Initialize
        if 'timestamps' in df.columns:
            if not x_timestamp.empty:
                last_input_timestamp = x_timestamp.iloc[-1]
                time_diff = df['timestamps'].iloc[1] - df['timestamps'].iloc[0] if len(df) > 1 else pd.Timedelta(hours=1)
                future_timestamps = pd.date_range(
                    start=last_input_timestamp + time_diff,
                    periods=pred_len,
                    freq=time_diff
                )
        else:
            # If no timestamps, use index relative to the end of input data
            future_timestamps = pd.Series(range(len(x_df), len(x_df) + pred_len))
        
        # Log predicted output time range
        if not future_timestamps.empty:
            if isinstance(future_timestamps.iloc[0], datetime.datetime):
                print(f"Prediction output covers time range: {future_timestamps.iloc[0].isoformat()} to {future_timestamps.iloc[-1].isoformat()}.")
            else: # range of integers
                print(f"Prediction output covers index range: {future_timestamps.iloc[0]} to {future_timestamps.iloc[-1]}.")
        else:
            print("No prediction output timestamps generated.")

        prediction_results = []
        for i, (_, row) in enumerate(pred_df.iterrows()):
            prediction_results.append({
                'timestamp': future_timestamps.iloc[i].isoformat() if i < len(future_timestamps) else f"T{i}",
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row['volume']) if 'volume' in row else 0.0, # ensure float type
                'amount': float(row['amount']) if 'amount' in row else 0.0
            })
        
        # Save prediction results to file
        try:
            save_prediction_results(
                file_path=file_path,
                prediction_type=prediction_type,
                prediction_results=prediction_results,
                actual_data=actual_data,
                input_data=x_df,
                prediction_params={
                    'lookback': lookback,
                    'pred_len': pred_len,
                    'temperature': temperature,
                    'top_p': top_p,
                    'sample_count': sample_count,
                    'start_date': start_date if start_date else 'latest'
                }
            )
        except Exception as e:
            print(f"Failed to save prediction results: {e}")
        
        return jsonify({
            'success': True,
            'prediction_type': prediction_type,
            'chart': chart_json,
            'prediction_results': prediction_results,
            'actual_data': actual_data,
            'has_comparison': not actual_df.empty,
            'message': f'Prediction completed, generated {pred_len} prediction points' + (f', including {len(actual_data)} actual data points for comparison' if not actual_df.empty else '')
        })
        
    except Exception as e:
        print(f"Error in /api/predict: {e}") # Added error log
        return jsonify({'error': f'Prediction failed: {str(e)}'}), 500

@app.route('/api/load-model', methods=['POST'])
def load_model():
    """Load Kronos model"""
    global tokenizer, model, predictor
    
    try:
        if not MODEL_AVAILABLE:
            return jsonify({'error': 'Kronos model library not available'}), 400
        
        data = request.get_json()
        model_key = data.get('model_key', 'kronos-small')
        device = data.get('device', 'cpu')
        
        if model_key not in AVAILABLE_MODELS:
            return jsonify({'error': f'Unsupported model: {model_key}'}), 400
        
        model_config = AVAILABLE_MODELS[model_key]
        
        # Load tokenizer and model
        tokenizer = KronosTokenizer.from_pretrained(model_config['tokenizer_id'])
        model = Kronos.from_pretrained(model_config['model_id'])
        
        # Create predictor
        predictor = KronosPredictor(model, tokenizer, device=device, max_context=model_config['context_length'])
        
        print(f"Kronos model loaded successfully: {model_config['name']} ({model_config['params']}) on {device}") # Added informative log

        return jsonify({
            'success': True,
            'message': f'Model loaded successfully: {model_config["name"]} ({model_config["params"]}) on {device}',
            'model_info': {
                'name': model_config['name'],
                'params': model_config['params'],
                'context_length': model_config['context_length'],
                'description': model_config['description']
            }
        })
        
    except Exception as e:
        print(f"Error in /api/load-model: {e}") # Added error log
        return jsonify({'error': f'Model loading failed: {str(e)}'}), 500

@app.route('/api/available-models')
def get_available_models():
    """Get available model list"""
    return jsonify({
        'models': AVAILABLE_MODELS,
        'model_available': MODEL_AVAILABLE
    })

@app.route('/api/model-status')
def get_model_status():
    """Get model status"""
    if MODEL_AVAILABLE:
        if predictor is not None:
            return jsonify({
                'available': True,
                'loaded': True,
                'message': 'Kronos model loaded and available',
                'current_model': {
                    'name': predictor.model.__class__.__name__,
                    'device': str(next(predictor.model.parameters()).device)
                }
            })
        else:
            return jsonify({
                'available': True,
                'loaded': False,
                'message': 'Kronos model available but not loaded'
            })
    else:
        return jsonify({
            'available': False,
            'loaded': False,
            'message': 'Kronos model library not available, please install related dependencies'
        })

@app.route('/api/latest-prediction')
def get_latest_prediction():
    """
    Get the latest saved prediction results.
    This endpoint facilitates displaying the most recent pre-computed prediction
    for a "live demo" context, assuming an external process regularly runs predictions
    and saves them using `save_prediction_results`.
    """
    latest_file_path = get_latest_prediction_file()
    if not latest_file_path:
        return jsonify({'success': False, 'message': 'No prediction results found'}), 404

    try:
        with open(latest_file_path, 'r', encoding='utf-8') as f:
            prediction_data = json.load(f)
        return jsonify({'success': True, 'prediction_data': prediction_data})
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {latest_file_path}: {e}")
        return jsonify({'success': False, 'error': f'Failed to parse latest prediction file: {str(e)}'}), 500
    except Exception as e:
        print(f"Failed to load latest prediction from {latest_file_path}: {e}")
        return jsonify({'success': False, 'error': f'Failed to load latest prediction: {str(e)}'}), 500

if __name__ == '__main__':
    print("Starting Kronos Web UI...")
    print(f"Model availability: {MODEL_AVAILABLE}")
    if MODEL_AVAILABLE:
        print("Tip: You can load Kronos model through /api/load-model endpoint")
    else:
        print("Tip: Kronos model library not found. Will use simulated data for demonstration if prediction logic were implemented (currently requires actual model for prediction).")
    
    app.run(debug=True, host='0.0.0.0', port=7070)