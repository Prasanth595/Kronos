"use client";

import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  CrosshairMode,
  LineStyle,
  type CandlestickData,
  type ChartOptions,
  type DeepPartial,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { PredictionResponse } from "@/features/kronos/types";

type PlotlyTrace = {
  x: string[];
  open: number[];
  high: number[];
  low: number[];
  close: number[];
  name?: string;
};

type PlotlyChartPayload = {
  data: PlotlyTrace[];
};

type PriceChartProps = {
  result: PredictionResponse | null;
};

const tradingViewDark = {
  background: "#171717",
  panel: "#171717",
  header: "#171717",
  border: "#222222",
  crosshair: "#758696",
  crosshairLabel: "#2A2E39",
  grid: "#1f2430",
  text: "#D1D4DC",
  mutedText: "#8a91a3",

  historyDown: "#EF5350",
  historyUp: "#26A69A",
  predictionDown: "#5B8DFF",
  predictionUp: "#2962FF",
  actualDown: "#FF5252",
  actualUp: "#FF9800",
};

const tradingViewDarkOptions: DeepPartial<ChartOptions> = {
  layout: {
    background: { type: ColorType.Solid, color: tradingViewDark.background },
    textColor: tradingViewDark.text,
    fontFamily: "Geist, Segoe UI, sans-serif",
  },
  grid: {
    vertLines: { color: tradingViewDark.grid },
    horzLines: { color: tradingViewDark.grid },
  },
  rightPriceScale: {
    borderColor: tradingViewDark.border,
    scaleMargins: { top: 0.12, bottom: 0.1 },
  },
  leftPriceScale: {
    borderColor: tradingViewDark.border,
  },
  timeScale: {
    borderColor: tradingViewDark.border,
    timeVisible: true,
    secondsVisible: false,
    rightOffset: 8,
    barSpacing: 8,
  },
  crosshair: {
    mode: CrosshairMode.Normal,
    vertLine: {
      color: tradingViewDark.crosshair,
      style: LineStyle.Dashed,
      width: 1,
      labelBackgroundColor: tradingViewDark.crosshairLabel,
    },
    horzLine: {
      color: tradingViewDark.crosshair,
      style: LineStyle.Dashed,
      width: 1,
      labelBackgroundColor: tradingViewDark.crosshairLabel,
    },
  },
};

function toCandles(trace: PlotlyTrace): CandlestickData<UTCTimestamp>[] {
  const length = Math.min(
    trace.x?.length ?? 0,
    trace.open?.length ?? 0,
    trace.high?.length ?? 0,
    trace.low?.length ?? 0,
    trace.close?.length ?? 0,
  );

  return Array.from({ length }, (_, index) => ({
    time: Math.floor(new Date(trace.x[index]).getTime() / 1000) as UTCTimestamp,
    open: Number(trace.open[index]),
    high: Number(trace.high[index]),
    low: Number(trace.low[index]),
    close: Number(trace.close[index]),
  }));
}

export function PriceChart({ result }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick">[]>([]);

  useEffect(() => {
    if (!containerRef.current || !result) return;

    const container = containerRef.current;
    container.innerHTML = "";
    container.style.backgroundColor = tradingViewDark.background;
    seriesRef.current = [];

    const chart = createChart(container, {
      autoSize: true,
      height: 560,
      ...tradingViewDarkOptions,
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    });

    chartRef.current = chart;
    chart.applyOptions(tradingViewDarkOptions);

    const styles = [
      {
        upColor: tradingViewDark.historyUp,
        downColor: tradingViewDark.historyDown,
        borderUpColor: tradingViewDark.historyUp,
        borderDownColor: tradingViewDark.historyDown,
        wickUpColor: tradingViewDark.historyUp,
        wickDownColor: tradingViewDark.historyDown,
      },
      {
        upColor: tradingViewDark.predictionUp,
        downColor: tradingViewDark.predictionDown,
        borderUpColor: tradingViewDark.predictionUp,
        borderDownColor: tradingViewDark.predictionDown,
        wickUpColor: tradingViewDark.predictionUp,
        wickDownColor: tradingViewDark.predictionDown,
      },
      {
        upColor: tradingViewDark.actualUp,
        downColor: tradingViewDark.actualDown,
        borderUpColor: tradingViewDark.actualUp,
        borderDownColor: tradingViewDark.actualDown,
        wickUpColor: tradingViewDark.actualUp,
        wickDownColor: tradingViewDark.actualDown,
      },
    ];

    const parsed = JSON.parse(result.chart) as PlotlyChartPayload;
    parsed.data.forEach((trace, index) => {
      const candles = toCandles(trace);
      if (!candles.length) return;

      const series = chart.addSeries(CandlestickSeries, {
        ...styles[index],
        priceFormat: {
          type: "price",
          precision: 4,
          minMove: 0.0001,
        },
      });
      series.setData(candles);
      seriesRef.current.push(series);
    });

    chart.timeScale().fitContent();
    window.requestAnimationFrame(() => {
      chart.applyOptions(tradingViewDarkOptions);
    });

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = [];
    };
  }, [result]);

  return (
    <Card 
      className="overflow-hidden border"
      style={{
        backgroundColor: tradingViewDark.panel,
        borderColor: tradingViewDark.border,
      }}>
      <CardHeader 
        className="flex flex-wrap items-center justify-between gap-3 px-5 py-4" 
        style={{
          backgroundColor: tradingViewDark.header,
          borderColor: tradingViewDark.border,
        }}>
        <div>
          <h2 className="text-lg font-semibold" style={{ color: tradingViewDark.text }}>
            Biểu đồ dự báo
          </h2>
          <p className="mt-1 text-sm" style={{ color: tradingViewDark.mutedText }}>
            Kéo để pan, cuộn chuột để zoom, rê chuột để xem crosshair.
          </p>
        </div>
        <Button
          variant="outline"
          className="h-9"
          onClick={() => chartRef.current?.timeScale().fitContent()}
          type="button"
        >
          Vừa khung
        </Button>
      </CardHeader>
      <Separator style={{ backgroundColor: tradingViewDark.border }} />

      <CardContent className="p-0" style={{ backgroundColor: tradingViewDark.background }}>
        <div
          className="flex flex-wrap gap-4 px-5 py-3 text-sm font-medium"
          style={{
            backgroundColor: tradingViewDark.header,
            color: tradingViewDark.mutedText,
            borderBottom: `1px solid ${tradingViewDark.border}`,
          }}>
          <span className="inline-flex items-center gap-2">
            <span
              className="size-2.5 rounded-full"
              style={{ backgroundColor: tradingViewDark.historyUp }}
            />
            Lịch sử
          </span>
          <span className="inline-flex items-center gap-2">
            <span
              className="size-2.5 rounded-full"
              style={{ backgroundColor: tradingViewDark.predictionUp }}
            />
            Dự báo
          </span>
          <span className="inline-flex items-center gap-2">
            <span
              className="size-2.5 rounded-full"
              style={{ backgroundColor: tradingViewDark.actualUp }}
            />
            Thực tế
          </span>
        </div>

        <div
          ref={containerRef}
          className="h-[560px] w-full overflow-hidden"
          style={{ backgroundColor: tradingViewDark.background }}
        />

        {!result && (
          <div
            className="flex h-[560px] items-center justify-center border-t text-sm"
            style={{ backgroundColor: tradingViewDark.background, color: tradingViewDark.text }}
          >
            Chưa có dữ liệu dự báo. Tải mô hình, tải dữ liệu, rồi bấm bắt đầu dự báo.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
