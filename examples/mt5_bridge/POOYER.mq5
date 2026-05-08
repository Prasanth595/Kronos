//+------------------------------------------------------------------+
//|                                                      POOYER.mq5 |
//|              Kronos Foundation Model -> MT5 Trading EA          |
//|              AURELIA EMPIRE | ZEROEMOTIONS | CLAUDE inside(TM)  |
//+------------------------------------------------------------------+
//
//  POOYER EA — MT5 EA powered by Kronos (AAAI-2026 foundation model)
//  trained on 45+ global exchanges.
//
//  Flow: EA collects OHLCV bars -> WebRequest -> POOYER Bridge (Python)
//        -> Kronos inference -> JSON signal -> EA executes trade
//
#property copyright "AURELIA EMPIRE | ZEROEMOTIONS"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

CTrade         trade;
CPositionInfo  pos;

//--- Inputs
input group "=== POOYER BRIDGE ==="
input string   BridgeURL        = "http://127.0.0.1:7799";
input int      BarsToSend       = 400;
input int      TimeoutMS        = 8000;

input group "=== SIGNAL FILTER ==="
input double   MinConfidence    = 0.45;
input string   AllowedDir       = "BOTH";
input int      MaxPositions     = 2;
input bool     UseKronosTP      = true;
input bool     UseKronosSL      = true;

input group "=== RISK MANAGEMENT ==="
input double   RiskPercent      = 1.0;
input double   MaxSpreadPoints  = 30.0;
input double   DailyLossLimit   = 3.0;
input double   FixedLots        = 0.01;

input group "=== ASYMMETRIC BREAKEVEN ==="
input bool     UseBreakeven     = true;
input double   BE_TriggerPips   = 3.0;
input double   BE_LockPips      = 0.5;

input group "=== SESSION FILTER ==="
input bool     UseKillHours     = true;
input int      KillHour1        = 10;
input int      KillHour2        = 17;
input bool     TradeMonday      = true;
input bool     TradeFriday      = false;

input group "=== MISC ==="
input int      MagicNumber      = 202600;
input string   TradeComment     = "POOYER-Kronos";
input bool     EnableLogging    = true;

//--- Globals
string   _symbol;
double   _point;
int      _digits;
double   _dailyStartBalance;
datetime _lastBarTime   = 0;
datetime _dailyResetTime= 0;
bool     _bridgeOK      = false;
int      _totalTrades   = 0;

struct KronosSignal {
   string direction;
   double confidence;
   double sl_pips;
   double tp_pips;
   double atr;
   double current_close;
   double forecast_end;
   double delta_pips;
   bool   valid;
};

//+------------------------------------------------------------------+
int OnInit()
{
   _symbol  = Symbol();
   _point   = Point();
   _digits  = Digits();
   _dailyStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(20);
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   Log("POOYER v1.0 initialized | " + _symbol);
   Log("Bridge: " + BridgeURL);
   Log("Min confidence: " + DoubleToString(MinConfidence, 2));
   Log("IMPORTANT: Add " + BridgeURL + " to Tools->Options->Expert Advisors->Allowed URLs");

   _bridgeOK = PingHealth();
   if(!_bridgeOK) Log("WARNING: Bridge not reachable — will retry on first bar");

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   Log("POOYER deinit. Total trades this session: " + IntegerToString(_totalTrades));
}

//+------------------------------------------------------------------+
void OnTick()
{
   datetime barTime = iTime(_symbol, PERIOD_CURRENT, 0);
   if(barTime == _lastBarTime) {
      ManageOpenPositions();
      return;
   }
   _lastBarTime = barTime;

   ResetDailyIfNeeded();

   if(!PassesSessionFilter())  { Log("Session filter: skip"); return; }
   if(!PassesDailyLossLimit()) { Log("Daily loss limit hit — halting new trades"); return; }
   if(!PingHealth())           { Log("Bridge offline — skipping bar"); return; }
   if(CountMyPositions() >= MaxPositions) { Log("Max positions reached"); return; }

   double spread = (double)SymbolInfoInteger(_symbol, SYMBOL_SPREAD) * _point * 10;
   if(spread > MaxSpreadPoints * _point * 10) {
      Log("Spread too high: " + DoubleToString(spread / _point, 1) + " pts");
      return;
   }

   KronosSignal sig;
   if(!FetchSignal(sig)) { Log("Signal fetch failed"); return; }

   Log(StringFormat("Kronos: %s conf=%.2f SL=%.5f TP=%.5f ATR=%.5f delta=%+.5f",
       sig.direction, sig.confidence, sig.sl_pips, sig.tp_pips, sig.atr, sig.delta_pips));

   if(sig.confidence < MinConfidence) {
      Log(StringFormat("Low confidence %.2f < %.2f — skip", sig.confidence, MinConfidence));
      return;
   }

   if(AllowedDir != "BOTH" && sig.direction != AllowedDir) {
      Log("Direction filter: skip " + sig.direction);
      return;
   }

   if(sig.direction == "BUY")  ExecuteTrade(ORDER_TYPE_BUY,  sig);
   if(sig.direction == "SELL") ExecuteTrade(ORDER_TYPE_SELL, sig);
}

//+------------------------------------------------------------------+
bool FetchSignal(KronosSignal &sig)
{
   sig.valid = false;
   string bars_json = BuildBarsJSON();
   if(bars_json == "") return false;

   string payload = "{\"symbol\":\"" + _symbol + "\",\"bars\":" + bars_json + "}";

   char   data[];
   char   result[];
   string headers = "Content-Type: application/json\r\n";
   string resp_headers;

   StringToCharArray(payload, data, 0, StringLen(payload));
   ArrayResize(data, ArraySize(data) - 1);

   int http_code = WebRequest("POST", BridgeURL + "/predict", headers,
                              TimeoutMS, data, result, resp_headers);

   if(http_code != 200) {
      Log("WebRequest failed: HTTP " + IntegerToString(http_code));
      return false;
   }

   string json = CharArrayToString(result);
   return ParseSignal(json, sig);
}

//+------------------------------------------------------------------+
string BuildBarsJSON()
{
   int bars = MathMin(BarsToSend, Bars(_symbol, PERIOD_CURRENT) - 1);
   if(bars < 50) return "";

   string j = "[";
   for(int i = bars - 1; i >= 1; i--) {
      j += StringFormat(
         "{\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%I64d}",
         iOpen(_symbol,PERIOD_CURRENT,i), iHigh(_symbol,PERIOD_CURRENT,i),
         iLow(_symbol,PERIOD_CURRENT,i),  iClose(_symbol,PERIOD_CURRENT,i),
         iVolume(_symbol,PERIOD_CURRENT,i)
      );
      if(i > 1) j += ",";
   }
   return j + "]";
}

//+------------------------------------------------------------------+
bool ParseSignal(const string &json, KronosSignal &sig)
{
   sig.direction    = ExtractString(json, "direction");
   sig.confidence   = ExtractDouble(json, "confidence");
   sig.sl_pips      = ExtractDouble(json, "sl_pips");
   sig.tp_pips      = ExtractDouble(json, "tp_pips");
   sig.atr          = ExtractDouble(json, "atr");
   sig.current_close= ExtractDouble(json, "current_close");
   sig.forecast_end = ExtractDouble(json, "forecast_end");
   sig.delta_pips   = ExtractDouble(json, "delta_pips");

   if(sig.direction == "" || sig.direction == "FLAT") return false;
   if(sig.sl_pips <= 0 || sig.tp_pips <= 0) return false;
   sig.valid = true;
   return true;
}

string ExtractString(const string &json, const string &key)
{
   string s = "\"" + key + "\":\"";
   int p = StringFind(json, s);
   if(p < 0) return "";
   p += StringLen(s);
   int e = StringFind(json, "\"", p);
   return (e < 0) ? "" : StringSubstr(json, p, e - p);
}

double ExtractDouble(const string &json, const string &key)
{
   string s = "\"" + key + "\":";
   int p = StringFind(json, s);
   if(p < 0) return 0.0;
   p += StringLen(s);
   string val = "";
   for(int i = p; i < p + 25; i++) {
      string ch = StringSubstr(json, i, 1);
      if(ch == "," || ch == "}" || ch == "]" || ch == " ") break;
      val += ch;
   }
   return StringToDouble(val);
}

//+------------------------------------------------------------------+
void ExecuteTrade(ENUM_ORDER_TYPE type, const KronosSignal &sig)
{
   double ask = SymbolInfoDouble(_symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_symbol, SYMBOL_BID);
   double price = (type == ORDER_TYPE_BUY) ? ask : bid;

   double sl_dist = UseKronosSL ? sig.sl_pips : BE_TriggerPips * 3 * _point * 10;
   double tp_dist = UseKronosTP ? sig.tp_pips : sl_dist * 2.0;

   double sl, tp;
   if(type == ORDER_TYPE_BUY) {
      sl = NormalizeDouble(price - sl_dist, _digits);
      tp = NormalizeDouble(price + tp_dist, _digits);
   } else {
      sl = NormalizeDouble(price + sl_dist, _digits);
      tp = NormalizeDouble(price - tp_dist, _digits);
   }

   double lots = CalcLots(sl_dist);
   string comment = TradeComment + StringFormat("|c=%.2f|atr=%.5f", sig.confidence, sig.atr);

   bool ok = (type == ORDER_TYPE_BUY)
      ? trade.Buy (lots, _symbol, price, sl, tp, comment)
      : trade.Sell(lots, _symbol, price, sl, tp, comment);

   if(ok) {
      _totalTrades++;
      Log(StringFormat("✓ %s %.2f lots @ %.5f SL=%.5f TP=%.5f",
          (type==ORDER_TYPE_BUY?"BUY":"SELL"), lots, price, sl, tp));
   } else {
      Log("✗ Order failed: " + IntegerToString(trade.ResultRetcode()) +
          " " + trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   if(!UseBreakeven) return;
   double pip = _point * 10;
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      if(!pos.SelectByIndex(i)) continue;
      if(pos.Magic() != MagicNumber || pos.Symbol() != _symbol) continue;
      double open_p = pos.PriceOpen();
      double cur_sl = pos.StopLoss();
      if(pos.PositionType() == POSITION_TYPE_BUY) {
         double cur = SymbolInfoDouble(_symbol, SYMBOL_BID);
         double be_sl = open_p + BE_LockPips * pip;
         if(cur >= open_p + BE_TriggerPips * pip && cur_sl < be_sl)
            trade.PositionModify(pos.Ticket(), NormalizeDouble(be_sl,_digits), pos.TakeProfit());
      } else {
         double cur = SymbolInfoDouble(_symbol, SYMBOL_ASK);
         double be_sl = open_p - BE_LockPips * pip;
         if(cur <= open_p - BE_TriggerPips * pip && cur_sl > be_sl)
            trade.PositionModify(pos.Ticket(), NormalizeDouble(be_sl,_digits), pos.TakeProfit());
      }
   }
}

//+------------------------------------------------------------------+
double CalcLots(double sl_dist)
{
   if(sl_dist <= 0) return FixedLots;
   double balance   = AccountInfoDouble(ACCOUNT_BALANCE);
   double risk_amt  = balance * RiskPercent / 100.0;
   double tick_val  = SymbolInfoDouble(_symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_size = SymbolInfoDouble(_symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick_val <= 0 || tick_size <= 0) return FixedLots;
   double lots = risk_amt / ((sl_dist / tick_size) * tick_val);
   double step = SymbolInfoDouble(_symbol, SYMBOL_VOLUME_STEP);
   lots = MathFloor(lots / step) * step;
   lots = MathMax(SymbolInfoDouble(_symbol,SYMBOL_VOLUME_MIN),
                  MathMin(SymbolInfoDouble(_symbol,SYMBOL_VOLUME_MAX), lots));
   return NormalizeDouble(lots, 2);
}

//+------------------------------------------------------------------+
bool PassesSessionFilter()
{
   if(!UseKillHours) return true;
   MqlDateTime t; TimeToStruct(TimeGMT(), t);
   if(t.hour == KillHour1 || t.hour == KillHour2) return false;
   if(!TradeMonday && t.day_of_week == 1) return false;
   if(!TradeFriday && t.day_of_week == 5) return false;
   return true;
}

bool PassesDailyLossLimit()
{
   double bal  = AccountInfoDouble(ACCOUNT_BALANCE);
   double loss = (_dailyStartBalance - bal) / _dailyStartBalance * 100.0;
   return loss < DailyLossLimit;
}

void ResetDailyIfNeeded()
{
   MqlDateTime t; TimeToStruct(TimeGMT(), t);
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d 00:00",t.year,t.mon,t.day));
   if(today > _dailyResetTime) {
      _dailyResetTime    = today;
      _dailyStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
      Log("Daily balance reset: " + DoubleToString(_dailyStartBalance, 2));
   }
}

int CountMyPositions()
{
   int count = 0;
   for(int i = PositionsTotal()-1; i >= 0; i--)
      if(pos.SelectByIndex(i) && pos.Magic()==MagicNumber && pos.Symbol()==_symbol) count++;
   return count;
}

bool PingHealth()
{
   char data[], result[]; string headers, resp_headers;
   int code = WebRequest("GET", BridgeURL+"/health", headers, 3000, data, result, resp_headers);
   _bridgeOK = (code == 200);
   return _bridgeOK;
}

void Log(const string &msg) { if(EnableLogging) PrintFormat("[POOYER] %s", msg); }
//+------------------------------------------------------------------+
