"""
KRONOS PURE — Close All Positions
Closes all open positions with MagicNumber 202602 via MT5 Python API.
"""
import sys
import time

MAGIC = 202602

try:
    import MetaTrader5 as mt5
except ImportError:
    print("Installing MetaTrader5 package...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "MetaTrader5"])
    import MetaTrader5 as mt5

print("=" * 50)
print("  KRONOS PURE — Close All Positions")
print(f"  Magic: {MAGIC}")
print("=" * 50)

if not mt5.initialize():
    print(f"ERROR: MT5 init failed — {mt5.last_error()}")
    print("Make sure MT5 is open and logged in.")
    input("\nPress Enter to exit...")
    sys.exit(1)

account = mt5.account_info()
print(f"\nAccount: {account.login} | Balance: {account.balance:.2f} {account.currency}")

positions = mt5.positions_get(symbol=None)
if positions is None:
    positions = []

kronos_pos = [p for p in positions if p.magic == MAGIC]

if not kronos_pos:
    print("\nNo open KRONOS_PURE positions found.")
else:
    print(f"\nFound {len(kronos_pos)} KRONOS_PURE position(s):\n")
    for p in kronos_pos:
        side  = "BUY" if p.type == 0 else "SELL"
        print(f"  #{p.ticket} {p.symbol} {side} {p.volume} lots | profit={p.profit:.2f}")

    print()
    confirm = input("Close all? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
    else:
        closed = 0
        for p in kronos_pos:
            tick  = mt5.symbol_info_tick(p.symbol)
            price = tick.bid if p.type == 0 else tick.ask  # BUY closes at bid, SELL at ask
            req   = {
                "action":   mt5.TRADE_ACTION_DEAL,
                "position": p.ticket,
                "symbol":   p.symbol,
                "volume":   p.volume,
                "type":     mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY,
                "price":    price,
                "deviation": 30,
                "magic":    MAGIC,
                "comment":  "KRONOS CLOSE ALL",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"  ✓ Closed #{p.ticket} {p.symbol}")
                closed += 1
            else:
                code = res.retcode if res else "N/A"
                print(f"  ✗ Failed #{p.ticket} — retcode {code}")
            time.sleep(0.2)

        print(f"\nDone. Closed {closed}/{len(kronos_pos)} positions.")

mt5.shutdown()
input("\nPress Enter to exit...")
