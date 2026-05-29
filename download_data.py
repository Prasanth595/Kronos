"""
Kronos - Downloader de dados de mercado
Baixa dados de qualquer ativo (cripto, acoes, forex) e salva em data/
para uso no Web UI.

Uso:
    python download_data.py XRP-USD        # XRP/USD - diario
    python download_data.py BTC-USD --interval 1h
    python download_data.py AAPL --interval 1d --period 2y
    python download_data.py ETH-USD --interval 5m --period 60d
    python download_data.py BTC-USD ETH-USD XRP-USD  # multiplos de uma vez

Intervalos suportados: 1m 2m 5m 15m 30m 60m 90m 1h 1d 5d 1wk 1mo
Periodos suportados  : 1d 5d 1mo 3mo 6mo 1y 2y 5y 10y ytd max
  (para intervalos < 1h, o maximo e 60 dias)
"""

import argparse
import os
import sys
import pandas as pd
import yfinance as yf

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def download(ticker: str, interval: str = "1d", period: str = "2y") -> None:
    print(f"  Baixando {ticker}  intervalo={interval}  periodo={period} ...")

    df = yf.download(ticker, interval=interval, period=period, progress=False, auto_adjust=True)

    if df.empty:
        print(f"  [ERRO] Nenhum dado retornado para '{ticker}'. Verifique o simbolo.")
        return

    # Flatten MultiIndex columns (yfinance retorna assim para tickers unicos as vezes)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower() for col in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]

    # Renomear colunas para o padrao Kronos
    rename = {"adj close": "close"}
    df = df.rename(columns=rename)

    # Garantir colunas obrigatorias
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"  [ERRO] Colunas faltando apos download: {missing}. Colunas presentes: {list(df.columns)}")
        return

    # Resetar index e renomear coluna de data/hora
    df = df.reset_index()
    time_col = df.columns[0]          # 'Datetime' ou 'Date'
    df = df.rename(columns={time_col: "timestamps"})
    df["timestamps"] = pd.to_datetime(df["timestamps"])

    # Remover timezone para evitar problemas de serializacao
    if df["timestamps"].dt.tz is not None:
        df["timestamps"] = df["timestamps"].dt.tz_convert("UTC").dt.tz_localize(None)

    # Manter apenas colunas uteis
    keep = ["timestamps", "open", "high", "low", "close"]
    if "volume" in df.columns:
        keep.append("volume")
    df = df[keep].dropna()

    # Nome do arquivo: TICKER_interval.csv
    safe_ticker = ticker.replace("/", "-").replace("=", "")
    filename = f"{safe_ticker}_{interval}.csv"
    out_path = os.path.join(DATA_DIR, filename)

    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(out_path, index=False)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"  [OK] {filename}  ({len(df)} candles, {size_kb:.1f} KB)  ->  data/{filename}")


def main():
    parser = argparse.ArgumentParser(
        description="Baixa dados de mercado e salva em data/ para uso no Kronos Web UI."
    )
    parser.add_argument("tickers", nargs="+", help="Simbolos yfinance (ex: XRP-USD BTC-USD AAPL)")
    parser.add_argument("--interval", default="1d",
                        help="Intervalo das velas (default: 1d). Ex: 5m 1h 1d")
    parser.add_argument("--period", default="2y",
                        help="Periodo historico (default: 2y). Ex: 60d 1y 5y max")
    args = parser.parse_args()

    print(f"\nKronos Data Downloader")
    print(f"Destino: {DATA_DIR}\n")

    for ticker in args.tickers:
        download(ticker.upper(), interval=args.interval, period=args.period)

    print(f"\nConcluido! Reinicie o servidor ou recarregue a pagina para ver os novos arquivos.")


if __name__ == "__main__":
    main()
