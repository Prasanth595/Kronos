import os
import sys

import yfinance as yf
import requests
import pandas as pd


def probar_kronos_api(ticker="BTC-USD", interval="5m", period="5d"):
    print(f"📥 Descargando últimos datos reales de {ticker} desde Yahoo Finance...")
    
    # 1. Extraer los datos reales del mercado
    try:
        data = yf.download(
            tickers=ticker,
            period=period,
            interval=interval,
            progress=False,
            timeout=30,
        )
    except Exception as exc:
        print(f"❌ Falló la descarga desde Yahoo Finance: {exc}")
        return False

    if data.empty:
        print("❌ No se pudieron descargar datos. Revisa el ticker o el intervalo.")
        return False

    # 2. Corregir y aplanar el MultiIndex de las versiones modernas de yfinance
    df = data.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)  # Quedarse solo con 'Open', 'High', etc.
    
    df = df.reset_index()
    
    # Normalizar los nombres de las columnas a minúsculas estrictas para Kronos
    df.columns = [str(col).lower() for col in df.columns]
    
    # Mapear la columna de tiempo de Yahoo Finance ('date' o 'datetime') al estándar del modelo
    if 'datetime' in df.columns:
        df = df.rename(columns={'datetime': 'timestamps'})
    elif 'date' in df.columns:
        df = df.rename(columns={'date': 'timestamps'})

    # Kronos requiere obligatoriamente una columna 'amount' (volumen monetario)
    df['amount'] = df['volume'] * df['close']
    
    # Convertir las marcas de tiempo a cadenas de texto legibles por JSON
    df['timestamps'] = pd.to_datetime(df['timestamps']).dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Extraer las últimas 400 velas como ventana de contexto (lookback)
    history_slice = df.tail(400).to_dict(orient='records')
    
    # 3. Preparar el paquete JSON de envío
    payload = {
        "history": history_slice,
        "pred_len": 120,   # Predecir las próximas 120 velas
        "freq": "5m"       # Frecuencia de las velas
    }
    
    # 4. Enviar los datos reales a la API de Kronos a través del puerto 7080
    url = os.environ.get("KRONOS_API_URL", "http://127.0.0.1:7080/predict")
    print("🧠 Enviando velas a Kronos en la GPU AMD para inferencia...")
    
    try:
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        predictions = response.json()
        pred_df = pd.DataFrame(predictions)
        expected_columns = ['timestamps', 'open', 'high', 'low', 'close']
        missing_columns = [column for column in expected_columns if column not in pred_df]
        if missing_columns:
            raise ValueError(
                "La API devolvió una respuesta inválida; faltan columnas: "
                + ", ".join(missing_columns)
            )

        print("\n✅ ¡Predicción recibida con éxito desde la GPU!")
        print("📈 Próximas velas estimadas por Kronos (Primeras 5 filas):")
        print(pred_df[expected_columns].head())
        return True
    except requests.ConnectionError:
        print(f"❌ No se pudo conectar con Kronos en {url}.")
        print("   Inicia la API con: cd ~/newBot/kronos/Kronos && ../kronos_env/bin/python examples/api_agent.py")
    except requests.RequestException as exc:
        print(f"❌ Error al llamar a la API de Kronos: {exc}")
        if exc.response is not None:
            print(exc.response.text)
    except (ValueError, TypeError) as exc:
        print(f"❌ Respuesta inválida de la API de Kronos: {exc}")

    return False

if __name__ == "__main__":
    # Activos para pruebas directas: "BTC-USD" (Crypto), "EURUSD=X" (Forex) o "AAPL" (Bolsa EE.UU.)
    sys.exit(0 if probar_kronos_api(ticker="BTC-USD", interval="5m", period="5d") else 1)
