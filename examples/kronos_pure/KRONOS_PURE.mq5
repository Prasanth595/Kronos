//+------------------------------------------------------------------+
//|                                              KRONOS_PURE.mq5     |
//|         Kronos-exclusive EA — 30-path Monte Carlo confluence     |
//|         M15/H1 native | 70% directional agreement threshold      |
//|         AURELIA EMPIRE | ZEROEMOTIONS | CLAUDE inside(TM)        |
//|         Merged: POOYER trade mgmt + KRONOS_PURE 30-path core     |
//+------------------------------------------------------------------+
#property copyright "AURELIA EMPIRE | ZEROEMOTIONS"
#property version   "2.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

CTrade        trade;
CPositionInfo pos;

//--- Inputs
input group "=== KRONOS PURE BRIDGE ==="
input string          BridgeURL        = "http://127.0.0.1:7900";
input string          AllowedSymbol    = "XAUUSD";
input ENUM_TIMEFRAMES StructureTF      = PERIOD_M5;
input int             BarsToSend       = 300;
input int             TimeoutMS        = 15000;

input group "=== SIGNAL FILTER ==="
input double          MinConfidence    = 0.35;        // variance-dampened — dir_agreement is the primary gate
input double          MinDirAgree      = 0.70;        // 70%+ → 54% actual WR | 80%+ → 58% WR (tune after 500 trades)
input double          MinRR            = 0.90;        // production baseline
input bool            UseBuy           = true;
input bool            UseSell          = true;
input bool            UseStructFilter  = false;       // Kronos BSQ already reads structure — disable to let it breathe

input group "=== SL BOUNDS ==="
input int             MinSLPoints      = 30;          // M1: 30pts | M15: 30  | BTCUSD: 50000
input int             MaxSLPoints      = 2000;        // M1: 400pts | M15: 2000 | BTCUSD: 300000

input group "=== EXIT CONDITIONS ==="
input bool            UseKronosExit    = true;
input int             RecheckSeconds   = 20;
input int             ForecastBars     = 4;

input group "=== BREAKEVEN ==="
input bool            UseBreakEven     = true;
input double          BEAtR            = 1.0;
input int             BEPlusPoints     = 20;          // XAUUSD: $0.20 buffer | BTCUSD: use 200

input group "=== TRAILING ==="
input bool            UseTrailing      = true;
input double          TrailStartR      = 1.3;
input double          TrailDistR       = 0.8;

input group "=== RISK ==="
input double          RiskPercent      = 0.5;
input double          MaxSpreadPts     = 25.0;        // XAUUSD | BTCUSD: use 2000
input double          DailyLossLimit   = 2.0;
input double          FixedLots        = 0.01;

input group "=== SESSION ==="
input bool            UseSession       = true;       // London/NY overlap only
input int             SessionStart     = 7;          // London open
input int             SessionEnd       = 20;          // NY close

input group "=== MISC ==="
input long            MagicNumber      = 202602;
input bool            EnableLogging    = true;

//--- Globals
datetime _lastBarTime    = 0;
datetime _lastRecheck    = 0;
double   _dayStartEquity = 0.0;
int      _dayOfYear      = -1;
int      _totalTrades    = 0;
string   _logFile        = "KRONOS_PURE_trades.csv";

// Per-position tracking (max 10)
ulong    _tk[10];
string   _dir[10];
double   _eConf[10];
double   _eAgree[10];
double   _eEntry[10];
double   _eSL[10];
double   _eTP[10];
double   _eATR[10];
double   _eSpread[10];
double   _eRR[10];
datetime _eTime[10];
int      _eLatMs[10];
string   _eSess[10];
double   _mfe[10];
double   _mae[10];
int      _posCount = 0;

struct KronosSignal {
   bool   ok;
   string direction;
   double confidence;
   double dir_agreement;
   int    buy_votes;
   int    sell_votes;
   double entry_ref;
   double path_tp;
   double path_sl;
   double atr;
   bool   should_exit;
   string reason;
};

//+------------------------------------------------------------------+
int OnInit()
{
   if(AllowedSymbol != "" && _Symbol != AllowedSymbol) {
      Log("Wrong symbol — expected " + AllowedSymbol);
      return INIT_FAILED;
   }
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(30);
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   if(Period() < PERIOD_M15)
      Log("WARNING: Attach to M15 or H1 — Kronos BSQ targets macro structure, not M1 noise");

   ResetDailyEquity();
   InitLogger();
   Log("KRONOS PURE v2.0 | " + _Symbol + " | TF=" + TFStr(Period()));
   Log("Add " + BridgeURL + " to Tools->Options->Expert Advisors->Allowed URLs");
   Log("Trade log: MQL5/Files/" + _logFile);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   Log("KRONOS PURE deinit. Trades: " + IntegerToString(_totalTrades));
}

//+------------------------------------------------------------------+
void OnTick()
{
   UpdateDailyState();
   ManageOpenPosition();

   if(IsDailyLossHit())    return;
   if(!IsNewBar())         return;
   if(HasOpenPosition())   return;
   if(!SessionOK())        { Log("Outside session — skip"); return; }
   if(!SpreadOK())         return;

   KronosSignal sig;
   if(!GetKronos("/predict", sig)) { Log("Signal fetch failed: " + sig.reason); return; }
   if(!sig.ok)                     { Log("No signal: " + sig.reason); return; }

   Log(StringFormat(
       "Kronos: %s agree=%.0f%% (%dB/%dS) conf=%.2f tp=%.5f sl=%.5f",
       sig.direction, sig.dir_agreement * 100, sig.buy_votes, sig.sell_votes,
       sig.confidence, sig.path_tp, sig.path_sl));

   if(sig.dir_agreement < MinDirAgree) {
      Log(StringFormat("Low agreement %.0f%% < %.0f%% — skip",
          sig.dir_agreement * 100, MinDirAgree * 100));
      return;
   }
   if(sig.confidence < MinConfidence - 0.001) {
      Log(StringFormat("Low confidence %.2f < %.2f — skip", sig.confidence, MinConfidence));
      return;
   }

   int bias = StructureBias();
   if(UseStructFilter) {
      if(sig.direction == "BUY"  && bias < 0) { Log("BUY blocked by structure"); return; }
      if(sig.direction == "SELL" && bias > 0) { Log("SELL blocked by structure"); return; }
   }

   if(sig.direction == "BUY"  && UseBuy)  TryOpen(ORDER_TYPE_BUY,  sig);
   if(sig.direction == "SELL" && UseSell) TryOpen(ORDER_TYPE_SELL, sig);
}

//+------------------------------------------------------------------+
void TryOpen(ENUM_ORDER_TYPE type, KronosSignal &sig)
{
   bool isBuy   = (type == ORDER_TYPE_BUY);
   double price = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                        : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl    = NormalizeDouble(sig.path_sl, _Digits);
   double tp    = NormalizeDouble(sig.path_tp, _Digits);
   string dir   = isBuy ? "BUY" : "SELL";

   if(isBuy  && (sl <= 0 || tp <= 0 || sl >= price || tp <= price)) { Log(dir + " invalid path"); return; }
   if(!isBuy && (sl <= 0 || tp <= 0 || sl <= price || tp >= price)) { Log(dir + " invalid path"); return; }

   double risk   = MathAbs(price - sl);
   double reward = MathAbs(tp - price);
   if(!SLDistOK(risk)) return;
   double rr = reward / risk;
   if(rr < MinRR) { Log(StringFormat("%s RR %.2f < %.2f — skip", dir, rr, MinRR)); return; }

   double lots = CalcLots(risk);
   if(lots <= 0) { Log(dir + " lot calc failed"); return; }

   string comment = "KRONOS|a=" + IntegerToString((int)(sig.dir_agreement * 100)) + "%";
   bool ok = isBuy ? trade.Buy(lots, _Symbol, price, sl, tp, comment)
                   : trade.Sell(lots, _Symbol, price, sl, tp, comment);

   if(ok) {
      _totalTrades++;
      ulong ticket = trade.ResultDeal();
      int spread   = (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
      double execPrice = trade.ResultPrice();
      int slipPts  = (int)MathRound(MathAbs(execPrice - price) / _Point);
      int latMs    = (int)((TimeCurrent() - iTime(_Symbol, PERIOD_CURRENT, 0)) * 1000);

      RegisterPos(ticket, dir, sig, sl, tp, rr, spread, slipPts, latMs, execPrice);

      Log(StringFormat("✓ %s %.2f lots @ %.5f SL=%.5f TP=%.5f agree=%.0f%% conf=%.2f RR=%.2f slip=%dpts",
          dir, lots, execPrice, sl, tp, sig.dir_agreement * 100, sig.confidence, rr, slipPts));
   } else {
      Log(dir + " failed: " + IntegerToString((int)trade.ResultRetcode())
          + " " + trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
void ManageOpenPosition()
{
   int type; ulong ticket;
   if(!GetCurrentPosition(type, ticket)) return;
   if(!PositionSelectByTicket(ticket))   return;

   double open  = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl    = PositionGetDouble(POSITION_SL);
   double tp    = PositionGetDouble(POSITION_TP);
   bool   isBuy = (type == POSITION_TYPE_BUY);
   double price = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                        : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double initRisk = MathAbs(open - sl);
   if(initRisk <= 0) return;
   double rNow = (isBuy ? (price - open) : (open - price)) / initRisk;

   // Breakeven
   if(UseBreakEven && rNow >= BEAtR) {
      double newSL = NormalizeDouble(
         isBuy ? open + BEPlusPoints * _Point : open - BEPlusPoints * _Point, _Digits);
      if((isBuy && newSL > sl) || (!isBuy && (sl == 0 || newSL < sl)))
         trade.PositionModify(ticket, newSL, tp);
   }

   // Trailing
   if(UseTrailing && rNow >= TrailStartR) {
      double dist  = initRisk * TrailDistR;
      double newSL = NormalizeDouble(isBuy ? price - dist : price + dist, _Digits);
      if((isBuy && newSL > sl) || (!isBuy && (sl == 0 || newSL < sl)))
         trade.PositionModify(ticket, newSL, tp);
   }

   // MFE / MAE tracking
   int idx = FindPosIdx(ticket);
   if(idx >= 0) {
      double excursion = (isBuy ? (price - open) : (open - price)) / initRisk;
      if(excursion > _mfe[idx]) _mfe[idx] = excursion;
      if(excursion < _mae[idx]) _mae[idx] = excursion;
   }

   // Kronos recheck (timer-based, not bar-based)
   if(UseKronosExit && TimeCurrent() - _lastRecheck >= RecheckSeconds) {
      _lastRecheck = TimeCurrent();
      KronosSignal rc;
      if(GetKronos("/recheck", rc) && rc.ok) {
         bool exitNow = rc.should_exit;
         if(isBuy  && rc.direction == "SELL" && rc.confidence >= MinConfidence) exitNow = true;
         if(!isBuy && rc.direction == "BUY"  && rc.confidence >= MinConfidence) exitNow = true;
         if(exitNow) {
            if(trade.PositionClose(ticket)) {
               Log(StringFormat("Closed by Kronos recheck — %s %.0f%% conf",
                   rc.direction, rc.confidence * 100));
               LogClose(ticket, "kronos_recheck");
            }
         }
      }
   }

   // TP / SL hit detection
   if(!PositionSelectByTicket(ticket)) {
      double closePrice = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double resultR    = (isBuy ? (closePrice - open) : (open - closePrice)) / initRisk;
      string reason     = resultR > 0 ? "tp" : "sl";
      LogClose(ticket, reason);
   }
}

//+------------------------------------------------------------------+
bool GetKronos(string endpoint, KronosSignal &sig)
{
   InitSignal(sig);
   string payload = BuildPayload();
   if(payload == "") { sig.reason = "payload empty"; return false; }
   string response;
   if(!PostJSON(endpoint, payload, response)) { sig.reason = response; return false; }
   ParseResponse(response, sig);
   return true;
}

void InitSignal(KronosSignal &s)
{
   s.ok=false; s.direction="FLAT"; s.confidence=0; s.dir_agreement=0;
   s.buy_votes=0; s.sell_votes=0; s.entry_ref=0; s.path_tp=0; s.path_sl=0;
   s.should_exit=false; s.reason="";
}

void ParseResponse(string json, KronosSignal &s)
{
   s.ok           = JsonBool  (json, "ok");
   s.direction    = JsonString(json, "direction");
   s.confidence   = JsonDouble(json, "confidence");
   s.dir_agreement= JsonDouble(json, "dir_agreement");
   s.buy_votes    = (int)JsonDouble(json, "buy_votes");
   s.sell_votes   = (int)JsonDouble(json, "sell_votes");
   s.entry_ref    = JsonDouble(json, "entry_ref");
   s.path_tp      = JsonDouble(json, "path_tp");
   s.path_sl      = JsonDouble(json, "path_sl");
   s.atr          = JsonDouble(json, "atr");
   s.should_exit  = JsonBool  (json, "should_exit");
   s.reason       = JsonString(json, "reason");
}

string BuildPayload()
{
   MqlRates rates[]; ArraySetAsSeries(rates, true);
   int copied = CopyRates(_Symbol, Period(), 0, BarsToSend, rates);
   if(copied < 60) return "";
   string j = "{";
   j += "\"symbol\":\"" + _Symbol + "\",";
   j += "\"freq\":\"" + PeriodToFreq() + "\",";
   j += "\"bars\":[";
   for(int i = copied - 1; i >= 0; i--) {
      j += StringFormat(
         "{\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.0f}",
         rates[i].open, rates[i].high, rates[i].low, rates[i].close,
         (double)rates[i].tick_volume);
      if(i > 0) j += ",";
   }
   j += "]}";
   return j;
}

bool PostJSON(string endpoint, string payload, string &response)
{
   char post[], result[];
   string headers = "Content-Type: application/json\r\n", rh;
   int sz = StringToCharArray(payload, post, 0, WHOLE_ARRAY, CP_UTF8);
   if(sz > 1) ArrayResize(post, sz - 1);  // strip null terminator — Flask rejects it
   ResetLastError();
   int status = WebRequest("POST", BridgeURL + endpoint, headers, TimeoutMS, post, result, rh);
   response = CharArrayToString(result, 0, -1, CP_UTF8);
   if(status == -1) {
      response = "WebRequest error " + IntegerToString(GetLastError()) + " — add " + BridgeURL + " to Allowed URLs";
      return false;
   }
   if(status < 200 || status >= 300) {
      Log("HTTP " + IntegerToString(status) + " " + endpoint);
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
int StructureBias()
{
   MqlRates r[]; ArraySetAsSeries(r, true);
   int n = CopyRates(_Symbol, StructureTF, 0, 80, r);
   if(n < 30) return 0;
   double emaFast = 0, emaSlow = 0;
   for(int i = 1; i <= 20; i++) emaFast += r[i].close;
   for(int i = 1; i <= 50; i++) emaSlow += r[i].close;
   emaFast /= 20.0; emaSlow /= 50.0;
   bool bullReclaim = r[1].low  < LowestLow(r,  2, 12) && r[1].close > r[1].open && r[1].close > r[2].close;
   bool bearReclaim = r[1].high > HighestHigh(r, 2, 12) && r[1].close < r[1].open && r[1].close < r[2].close;
   if(bullReclaim) return  1;
   if(bearReclaim) return -1;
   if(emaFast > emaSlow) return  1;
   if(emaFast < emaSlow) return -1;
   return 0;
}

double LowestLow(MqlRates &r[], int start, int count)
{
   double v = DBL_MAX;
   for(int i = start; i < start + count && i < ArraySize(r); i++)
      if(r[i].low < v) v = r[i].low;
   return v;
}

double HighestHigh(MqlRates &r[], int start, int count)
{
   double v = -DBL_MAX;
   for(int i = start; i < start + count && i < ArraySize(r); i++)
      if(r[i].high > v) v = r[i].high;
   return v;
}

bool SLDistOK(double risk)
{
   int pts = (int)MathRound(risk / _Point);
   if(pts < MinSLPoints) { Log("SL too tight: " + IntegerToString(pts) + " pts"); return false; }
   if(pts > MaxSLPoints) { Log("SL too wide: "  + IntegerToString(pts) + " pts"); return false; }
   return true;
}

double CalcLots(double priceRisk)
{
   if(priceRisk <= 0) return FixedLots;
   double equity   = AccountInfoDouble(ACCOUNT_EQUITY);
   double riskAmt  = equity * RiskPercent / 100.0;
   double tickSz   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickVal  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSz <= 0 || tickVal <= 0) return FixedLots;
   double lossPerLot = (priceRisk / tickSz) * tickVal;
   if(lossPerLot <= 0) return FixedLots;
   double lots = riskAmt / lossPerLot;
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   lots = MathMax(minL, MathMin(maxL, MathFloor(lots / step) * step));
   return NormalizeDouble(lots, 2);
}

bool HasOpenPosition() { int t; ulong tk; return GetCurrentPosition(t, tk); }

bool GetCurrentPosition(int &posType, ulong &ticket)
{
   for(int i = PositionsTotal()-1; i >= 0; i--) {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == MagicNumber) {
         posType = (int)PositionGetInteger(POSITION_TYPE);
         ticket  = tk;
         return true;
      }
   }
   return false;
}

bool IsNewBar()
{
   datetime t = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(t <= 0 || t == _lastBarTime) return false;
   _lastBarTime = t;
   return true;
}

bool SessionOK()
{
   if(!UseSession) return true;
   MqlDateTime dt; TimeToStruct(TimeGMT(), dt);   // UTC — SessionStart/End are UTC hours
   return (dt.hour >= SessionStart && dt.hour < SessionEnd);
}

bool SpreadOK()
{
   int spread = (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(spread > MaxSpreadPts) { Log("Spread too high: " + IntegerToString(spread)); return false; }
   return true;
}

bool IsDailyLossHit()
{
   double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
   double max = _dayStartEquity * DailyLossLimit / 100.0;
   if(_dayStartEquity - eq >= max) { Log("Daily loss cap hit"); return true; }
   return false;
}

void ResetDailyEquity()
{
   MqlDateTime dt; TimeToStruct(TimeCurrent(), dt);
   _dayOfYear      = dt.day_of_year;
   _dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
}

void UpdateDailyState()
{
   MqlDateTime dt; TimeToStruct(TimeCurrent(), dt);
   if(dt.day_of_year != _dayOfYear) ResetDailyEquity();
}

string PeriodToFreq()
{
   switch(Period()) {
      case PERIOD_M1:  return "1min";
      case PERIOD_M5:  return "5min";
      case PERIOD_M15: return "15min";
      case PERIOD_M30: return "30min";
      case PERIOD_H1:  return "1h";
      case PERIOD_H4:  return "4h";
      case PERIOD_D1:  return "1D";
      default:         return "15min";
   }
}

string TFStr(ENUM_TIMEFRAMES tf)
{
   switch(tf) {
      case PERIOD_M1:  return "M1";  case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15"; case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";  case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";  default:         return "?";
   }
}

string JsonString(string json, string key)
{
   string pat = "\"" + key + "\":\"";
   int p = StringFind(json, pat); if(p < 0) return "";
   p += StringLen(pat);
   int e = StringFind(json, "\"", p); if(e < 0) return "";
   return StringSubstr(json, p, e - p);
}

double JsonDouble(string json, string key)
{
   string pat = "\"" + key + "\":";
   int p = StringFind(json, pat); if(p < 0) return 0.0;
   p += StringLen(pat);
   int e1 = StringFind(json, ",", p);
   int e2 = StringFind(json, "}", p);
   int e  = (e1 < 0 ? e2 : (e2 < 0 ? e1 : MathMin(e1, e2)));
   if(e < 0) return 0.0;
   return StringToDouble(StringSubstr(json, p, e - p));
}

bool JsonBool(string json, string key)
{
   string pat = "\"" + key + "\":";
   int p = StringFind(json, pat); if(p < 0) return false;
   p += StringLen(pat);
   return StringFind(StringSubstr(json, p, 5), "true") == 0;
}

void Log(string msg) { if(EnableLogging) PrintFormat("[KRONOS_PURE] %s", msg); }

//+------------------------------------------------------------------+
// LOGGER
//+------------------------------------------------------------------+
void InitLogger()
{
   int fh = FileOpen(_logFile, FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
   if(fh == INVALID_HANDLE) { Log("Logger: cannot create " + _logFile); return; }
   FileWrite(fh,
      "time","symbol","direction","dir_agreement","confidence",
      "rr","entry","sl","tp","spread_pts","slippage_pts","latency_ms",
      "session","atr","result_R","mfe_R","mae_R","hold_minutes","exit_reason");
   FileClose(fh);
}

string SessionName()
{
   MqlDateTime t; TimeToStruct(TimeGMT(), t);
   int h = t.hour;
   if(h >= 7  && h < 10) return "london_open";
   if(h >= 10 && h < 13) return "london_core";
   if(h >= 13 && h < 17) return "ny_overlap";
   if(h >= 17 && h < 20) return "ny_close";
   return "off_session";
}

void RegisterPos(ulong ticket, string dir, KronosSignal &sig,
                 double sl, double tp, double rr,
                 int spread, int slip, int latMs, double execPrice)
{
   if(_posCount >= 10) return;
   int i = _posCount;
   _tk[i]     = ticket;
   _dir[i]    = dir;
   _eConf[i]  = sig.confidence;
   _eAgree[i] = sig.dir_agreement;
   _eEntry[i] = execPrice;
   _eSL[i]    = sl;
   _eTP[i]    = tp;
   _eATR[i]   = sig.atr;
   _eSpread[i]= spread;
   _eRR[i]    = rr;
   _eTime[i]  = TimeCurrent();
   _eLatMs[i] = latMs;
   _eSess[i]  = SessionName();
   _mfe[i]    = 0.0;
   _mae[i]    = 0.0;
   _posCount++;
}

int FindPosIdx(ulong ticket)
{
   for(int i = 0; i < _posCount; i++)
      if(_tk[i] == ticket) return i;
   return -1;
}

void RemovePos(int idx)
{
   for(int i = idx; i < _posCount - 1; i++) {
      _tk[i]     = _tk[i+1];     _dir[i]    = _dir[i+1];
      _eConf[i]  = _eConf[i+1];  _eAgree[i] = _eAgree[i+1];
      _eEntry[i] = _eEntry[i+1]; _eSL[i]    = _eSL[i+1];
      _eTP[i]    = _eTP[i+1];    _eATR[i]   = _eATR[i+1];
      _eSpread[i]= _eSpread[i+1];_eRR[i]    = _eRR[i+1];
      _eTime[i]  = _eTime[i+1];  _eLatMs[i] = _eLatMs[i+1];
      _eSess[i]  = _eSess[i+1];  _mfe[i]    = _mfe[i+1];
      _mae[i]    = _mae[i+1];
   }
   _posCount--;
}

void LogClose(ulong ticket, string exitReason)
{
   int idx = FindPosIdx(ticket);
   if(idx < 0) return;

   bool   isBuy   = (_dir[idx] == "BUY");
   double closePrice = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                             : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double initRisk   = MathAbs(_eEntry[idx] - _eSL[idx]);
   double resultR    = initRisk > 0
      ? (isBuy ? (closePrice - _eEntry[idx]) : (_eEntry[idx] - closePrice)) / initRisk
      : 0.0;
   int holdMin = (int)((TimeCurrent() - _eTime[idx]) / 60);

   int fh = FileOpen(_logFile, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
   if(fh != INVALID_HANDLE) {
      FileSeek(fh, 0, SEEK_END);
      FileWrite(fh,
         TimeToString(_eTime[idx], TIME_DATE|TIME_SECONDS),
         _Symbol,
         _dir[idx],
         DoubleToString(_eAgree[idx], 2),
         DoubleToString(_eConf[idx],  2),
         DoubleToString(_eRR[idx],    2),
         DoubleToString(_eEntry[idx], _Digits),
         DoubleToString(_eSL[idx],    _Digits),
         DoubleToString(_eTP[idx],    _Digits),
         IntegerToString((int)_eSpread[idx]),
         IntegerToString(_eLatMs[idx] < 0 ? 0 : (int)_eSpread[idx]),
         IntegerToString(_eLatMs[idx]),
         _eSess[idx],
         DoubleToString(_eATR[idx],   5),
         DoubleToString(resultR,      3),
         DoubleToString(_mfe[idx],    3),
         DoubleToString(_mae[idx],    3),
         IntegerToString(holdMin),
         exitReason);
      FileClose(fh);
   }

   Log(StringFormat("LOG: %s %s result=%.2fR mfe=%.2fR mae=%.2fR held=%dmin exit=%s",
       _dir[idx], _Symbol, resultR, _mfe[idx], _mae[idx], holdMin, exitReason));

   RemovePos(idx);
}
//+------------------------------------------------------------------+
