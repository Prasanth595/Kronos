# Guardar como examples/api_agent.py
import sys
from pathlib import Path

from flask import Flask, request, jsonify
import numpy as np
import pandas as pd
import torch

# Permite ejecutar directamente: python examples/api_agent.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
   sys.path.insert(0, str(PROJECT_ROOT))

from model import Kronos, KronosTokenizer, KronosPredictor

app = Flask(__name__)

# Inicializar modelo de forma global
tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-base")
tokenizer.eval()
model.eval()
predictor = KronosPredictor(model, tokenizer, max_context=512)

@app.route('/predict', methods=['POST'])
def get_prediction():
   data = request.json
   seed = data.get('seed')
   if seed is not None:
      seed = int(seed)
      np.random.seed(seed)
      torch.manual_seed(seed)
      if torch.cuda.is_available():
         torch.cuda.manual_seed_all(seed)
   # Convertir el JSON entrante de OpenClaw a DataFrame de Pandas
   df = pd.DataFrame(data['history'])
   df['timestamps'] = pd.to_datetime(df['timestamps'])

   # Extraer timestamps futuros (simulados o enviados por el bot)
   pred_len = data.get('pred_len', 120)
   # Generar marcas de tiempo futuras basadas en la frecuencia (ej. 5min)
   freq = data.get('freq', '5min')
   # En pandas, "m" significa fin de mes; Yahoo usa "m" para minutos.
   if isinstance(freq, str) and freq.endswith('m') and freq[:-1].isdigit():
      freq = f"{freq[:-1]}min"
   y_timestamp = pd.Series(
      pd.date_range(
         start=df['timestamps'].iloc[-1],
         periods=pred_len + 1,
         freq=freq,
      )[1:]
   )

   # Inferencia en GPU AMD (vía PyTorch ROCm)
   pred_df = predictor.predict(
       df=df[['open', 'high', 'low', 'close', 'volume', 'amount']],
       x_timestamp=df['timestamps'],
       y_timestamp=y_timestamp,
       pred_len=pred_len
   )

   pred_df.index.name = 'timestamps'
   return jsonify(pred_df.reset_index().to_dict(orient='records'))

if __name__ == '__main__':
   # Sólo localhost: esta API no tiene autenticación y no debe exponerse a la red.
   app.run(host='127.0.0.1', port=7080, threaded=False)
