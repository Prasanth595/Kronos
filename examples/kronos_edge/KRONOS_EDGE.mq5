//+------------------------------------------------------------------+
//|                                              KRONOS_EDGE.mq5     |
//|         Full Kronos Skill EA — Ensemble Confidence + Path SL/TP  |
//|         Flip-Resistant Exit + Forecast Expiry                    |
//|         AURELIA EMPIRE | ZEROEMOTIONS | CLAUDE inside(TM)        |
//+------------------------------------------------------------------+
//
//  v1.1 fixes:
//    - StringToCharArray null-terminator bug (malformed JSON to bridge)
//    - Session filter: proper London/NY window instead of 2 kill-hours
//    - SL/TP direction validation (guards invalid path levels)
//    - SL bounds guard (min/max points)
//    - Removed dead NO_TRADE branch (eliminated in bridge)
//
#property copyright "AURELIA EMPIRE | ZEROEMOTIONS"
#property version   "1.10"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

CTrade        trade;
CPositionInfo pos;

//--- Inputs
input group "=== KRONOS EDGE BRIDGE ==="
input string  BridgeURL         = "http://127.0.0.1:7800";
input int     BarsToSend        = 400;
input int     TimeoutMS         = 10000;

input group "=== SIGNAL FILTER ==="
input double  MinConfidence     = 0.40;
input string  AllowedDir        = "BOTH";
input int     MaxPositions      = 2;

input group "=== EXIT CONDITIONS ==="
input int     FlipsToExit       = 2;
input double  ConfCollapseRatio = 0.50;
input int     ForecastBars      = 5;

input group "=== RISK ==="
input double  RiskPercent       = 1.0;
input double  MaxSpreadPoints   = 30.0;
input double  DailyLossLimit    = 3.0;
input double  FixedLots         = 0.01;

input group "=== RISK BOUNDS ==="
input int     MinSLPoints       = 30;          // minimum SL distance in points
input int     MaxSLPoints       = 2000;        // maximum SL distance in points

input group "=== SESSION ==="
input bool    UseSession        = true;        // restrict to London/NY overlap
input int     SessionStart      = 7;           // session open hour (UTC)
input int     SessionEnd        = 20;          // session close hour (UTC)
input bool    TradeMonday       = true;
input bool    TradeFriday       = false;

input group "=== MISC ==="
input int     MagicNumber       = 202601;
input string  TradeComment      = "KRONOS-EDGE";
input bool    EnableLogging     = true;

//--- Globals
string   _symbol;
double   _point;
int      _digits;
double   _dailyStartBalance;
datetime _lastBarTime    = 0;
datetime _dailyResetTime = 0;
bool     _bridgeOK       = false;
int      _totalTrades    = 0;

struct KronosEdgeSignal {
   string signal_state;
   double confidence;
   double path_tp;
   double path_sl;
   bool   sl_capped;
   double atr;
   bool   valid;
};

struct RecheckResult {
   string direction;
   double confidence;
   bool   valid;
};

// Per-position tracking (max 10 simultaneous)
ulong  _ticket[10];
string _entry_dir[10];
double _entry_conf[10];
int    _bars_held[10];
int    _flip_count[10];
int    _trade_count = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   _symbol = Symbol();
   _point  = Point();
   _digits = Digits();
   _dailyStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(20);
   trade.SetTypeFilling(ORDER_FILLING_IOC);
   Log("KRONOS EDGE v1.0 | " + _symbol + " | Bridge: " + BridgeURL);
   Log("IMPORTANT: Add " + BridgeURL + " to Tools->Options->Expert Advisors->Allowed URLs");
   _bridgeOK = PingHealth();
   if(!_bridgeOK) Log("WARNING: Bridge not reachable — will retry on first bar");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   Log("KRONOS EDGE deinit. Trades this session: " + IntegerToString(_totalTrades));
}

//+------------------------------------------------------------------+
void OnTick()
{
   datetime barTime = iTime(_symbol, PERIOD_CURRENT, 0);
   if(barTime == _lastBarTime) return;
   _lastBarTime = barTime;

   ResetDailyIfNeeded();
   ManageByRecheck();

   if(!PassesSessionFilter())  { Log("Session filter: skip"); return; }
   if(!PassesDailyLossLimit()) { Log("Daily loss limit — halting"); return; }
   if(!PingHealth())           { Log("Bridge offline — skip bar"); return; }
   if(CountMyPositions() >= MaxPositions) return;

   double spread = (double)SymbolInfoInteger(_symbol, SYMBOL_SPREAD) * _point * 10;
   if(spread > MaxSpreadPoints * _point * 10) { Log("Spread too high — skip"); return; }

   KronosEdgeSignal sig;
   if(!FetchSignal(sig)) { Log("Signal fetch failed"); return; }

   Log(StringFormat("Kronos: %s conf=%.2f path_tp=%.5f path_sl=%.5f atr=%.5f%s",
       sig.signal_state, sig.confidence, sig.path_tp, sig.path_sl, sig.atr,
       sig.sl_capped ? " [SL CAPPED]" : ""));

   if(sig.signal_state == "FLAT") { Log("FLAT — " + sig.signal_state); return; }
   if(sig.confidence < MinConfidence) {
      Log(StringFormat("Low confidence %.2f < %.2f — skip", sig.confidence, MinConfidence));
      return;
   }
   if(AllowedDir != "BOTH" && sig.signal_state != AllowedDir) {
      Log("Direction filter: skip " + sig.signal_state); return;
   }

   if(sig.signal_state == "BUY")  ExecuteTrade(ORDER_TYPE_BUY,  sig);
   if(sig.signal_state == "SELL") ExecuteTrade(ORDER_TYPE_SELL, sig);
}

//+------------------------------------------------------------------+
void ManageByRecheck()
{
   if(_trade_count == 0) return;
   string bars_json = BuildBarsJSON();
   if(bars_json == "") return;

   for(int i = _trade_count - 1; i >= 0; i--)
   {
      if(!pos.SelectByTicket(_ticket[i])) {
         RemoveTradeEntry(i);
         continue;
      }
      if(pos.Magic() != MagicNumber || pos.Symbol() != _symbol) continue;

      _bars_held[i]++;

      if(_bars_held[i] >= ForecastBars) {
         Log(StringFormat("Ticket %d: forecast expired (%d bars) — closing",
             (int)_ticket[i], _bars_held[i]));
         trade.PositionClose(_ticket[i]);
         RemoveTradeEntry(i);
         continue;
      }

      RecheckResult rc;
      if(!FetchRecheck(bars_json, rc)) continue;

      if(rc.direction != _entry_dir[i] && rc.direction != "FLAT")
         _flip_count[i]++;
      else
         _flip_count[i] = 0;

      bool exit_flip = (_flip_count[i] >= FlipsToExit);
      bool exit_conf = (rc.confidence < _entry_conf[i] * ConfCollapseRatio);

      if(exit_flip || exit_conf) {
         string reason = exit_flip ? "consecutive flips" : "confidence collapse";
         Log(StringFormat("Ticket %d: exit — %s (flips=%d conf=%.2f)",
             (int)_ticket[i], reason, _flip_count[i], rc.confidence));
         trade.PositionClose(_ticket[i]);
         RemoveTradeEntry(i);
      }
   }
}

//+------------------------------------------------------------------+
void ExecuteTrade(ENUM_ORDER_TYPE type, const KronosEdgeSignal &sig)
{
   bool isBuy   = (type == ORDER_TYPE_BUY);
   double ask   = SymbolInfoDouble(_symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_symbol, SYMBOL_BID);
   double price = isBuy ? ask : bid;
   double sl    = NormalizeDouble(sig.path_sl, _digits);
   double tp    = NormalizeDouble(sig.path_tp, _digits);

   // Direction validation — path_sl and path_tp must be on correct side
   if(isBuy  && (sl <= 0 || tp <= 0 || sl >= price || tp <= price)) { Log("BUY: invalid path levels"); return; }
   if(!isBuy && (sl <= 0 || tp <= 0 || sl <= price || tp >= price)) { Log("SELL: invalid path levels"); return; }

   // SL bounds guard
   double sl_dist = MathAbs(price - sl);
   int    sl_pts  = (int)MathRound(sl_dist / _point);
   if(sl_pts < MinSLPoints) { Log("SL too tight: " + IntegerToString(sl_pts) + " pts — skip"); return; }
   if(sl_pts > MaxSLPoints) { Log("SL too wide: "  + IntegerToString(sl_pts) + " pts — skip"); return; }

   double lots  = CalcLots(sl_dist);
   string full_comment = TradeComment + StringFormat("|c=%.2f|e=%d", sig.confidence, ForecastBars);
   string comment      = StringSubstr(full_comment, 0, 31);

   bool ok = (type == ORDER_TYPE_BUY)
      ? trade.Buy (lots, _symbol, price, sl, tp, comment)
      : trade.Sell(lots, _symbol, price, sl, tp, comment);

   if(ok) {
      ulong  ticket = trade.ResultDeal();
      string dir    = (type == ORDER_TYPE_BUY) ? "BUY" : "SELL";
      _totalTrades++;
      RegisterTrade(ticket, dir, sig.confidence);
      Log(StringFormat("✓ %s %.2f lots @ %.5f SL=%.5f TP=%.5f conf=%.2f",
          dir, lots, price, sl, tp, sig.confidence));
   } else {
      Log("✗ Order failed: " + IntegerToString(trade.ResultRetcode())
          + " " + trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
bool FetchSignal(KronosEdgeSignal &sig)
{
   sig.valid = false;
   string bars_json = BuildBarsJSON();
   if(bars_json == "") return false;
   string payload = "{\"symbol\":\"" + _symbol + "\",\"bars\":" + bars_json + "}";
   char data[], result[]; string headers = "Content-Type: application/json\r\n", rh;
   int sz = StringToCharArray(payload, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(sz > 1) ArrayResize(data, sz - 1);
   int code = WebRequest("POST", BridgeURL + "/predict", headers, TimeoutMS, data, result, rh);
   if(code != 200) { Log("HTTP " + IntegerToString(code)); return false; }
   return ParseEdgeSignal(CharArrayToString(result), sig);
}

bool FetchRecheck(const string &bars_json, RecheckResult &rc)
{
   rc.valid = false;
   string payload = "{\"symbol\":\"" + _symbol + "\",\"bars\":" + bars_json + "}";
   char data[], result[]; string headers = "Content-Type: application/json\r\n", rh;
   int sz = StringToCharArray(payload, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(sz > 1) ArrayResize(data, sz - 1);
   int code = WebRequest("POST", BridgeURL + "/recheck", headers, 5000, data, result, rh);
   if(code != 200) return false;
   string json   = CharArrayToString(result);
   rc.direction  = ExtractString(json, "direction");
   rc.confidence = ExtractDouble(json, "confidence");
   rc.valid      = (rc.direction != "");
   return rc.valid;
}

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
         iVolume(_symbol,PERIOD_CURRENT,i));
      if(i > 1) j += ",";
   }
   return j + "]";
}

//+------------------------------------------------------------------+
bool ParseEdgeSignal(const string &json, KronosEdgeSignal &sig)
{
   sig.signal_state = ExtractString(json, "signal_state");
   sig.confidence   = ExtractDouble(json, "confidence");
   sig.path_tp      = ExtractDouble(json, "path_tp");
   sig.path_sl      = ExtractDouble(json, "path_sl");
   sig.atr          = ExtractDouble(json, "atr");
   sig.sl_capped    = (StringFind(json, "\"sl_capped\":true") >= 0);
   sig.valid        = (sig.signal_state != "");
   return sig.valid;
}

string ExtractString(const string &json, const string &key)
{
   string s = "\"" + key + "\":\"";
   int p = StringFind(json, s); if(p < 0) return "";
   p += StringLen(s);
   int e = StringFind(json, "\"", p);
   return (e < 0) ? "" : StringSubstr(json, p, e - p);
}

double ExtractDouble(const string &json, const string &key)
{
   string s = "\"" + key + "\":";
   int p = StringFind(json, s); if(p < 0) return 0.0;
   p += StringLen(s);
   string val = "";
   for(int i = p; i < p + 25; i++) {
      string ch = StringSubstr(json, i, 1);
      if(ch == "," || ch == "}" || ch == "]" || ch == " ") break;
      val += ch;
   }
   return StringToDouble(val);
}

void RegisterTrade(ulong ticket, string dir, double conf)
{
   if(_trade_count >= 10) return;
   _ticket[_trade_count]     = ticket;
   _entry_dir[_trade_count]  = dir;
   _entry_conf[_trade_count] = conf;
   _bars_held[_trade_count]  = 0;
   _flip_count[_trade_count] = 0;
   _trade_count++;
}

void RemoveTradeEntry(int idx)
{
   for(int i = idx; i < _trade_count - 1; i++) {
      _ticket[i]     = _ticket[i+1];
      _entry_dir[i]  = _entry_dir[i+1];
      _entry_conf[i] = _entry_conf[i+1];
      _bars_held[i]  = _bars_held[i+1];
      _flip_count[i] = _flip_count[i+1];
   }
   _trade_count--;
}

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
   lots = MathMax(SymbolInfoDouble(_symbol, SYMBOL_VOLUME_MIN),
                  MathMin(SymbolInfoDouble(_symbol, SYMBOL_VOLUME_MAX), lots));
   return NormalizeDouble(lots, 2);
}

int CountMyPositions()
{
   int count = 0;
   for(int i = PositionsTotal()-1; i >= 0; i--)
      if(pos.SelectByIndex(i) && pos.Magic()==MagicNumber && pos.Symbol()==_symbol) count++;
   return count;
}

bool PassesSessionFilter()
{
   if(!UseSession) return true;
   MqlDateTime t; TimeToStruct(TimeGMT(), t);   // UTC — SessionStart/End are UTC hours
   if(!TradeMonday && t.day_of_week == 1) return false;
   if(!TradeFriday && t.day_of_week == 5) return false;
   return (t.hour >= SessionStart && t.hour < SessionEnd);
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
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d 00:00", t.year, t.mon, t.day));
   if(today > _dailyResetTime) {
      _dailyResetTime    = today;
      _dailyStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
      Log("Daily balance reset: " + DoubleToString(_dailyStartBalance, 2));
   }
}

bool PingHealth()
{
   char data[], result[]; string headers, rh;
   int code = WebRequest("GET", BridgeURL + "/health", headers, 1500, data, result, rh);
   _bridgeOK = (code == 200);
   return _bridgeOK;
}

void Log(const string &msg) { if(EnableLogging) PrintFormat("[KRONOS_EDGE] %s", msg); }
//+------------------------------------------------------------------+
