"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  PriceScaleMode,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LogicalRange,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

type Kline = {
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  updated_at_ms: string;
  open_time_ms?: string;
};

type Props = {
  chartKey: string;
  priceScaleMode: "linear" | "log";
  uiTheme: "light" | "dark";
  klines: Kline[];
  loading: boolean;
  error: string | null;
  onNeedMoreHistory?: () => void;
  canLoadMoreHistory?: boolean;
  isLoadingMoreHistory?: boolean;
};

type CandleDatum = {
  time: UTCTimestamp;
  timeMs: number;
  volume: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

type CrosshairSnapshot = {
  timeLabel: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
};

function parseKlineTimeMs(kline: Kline): number {
  const openTimeMs = Number.parseInt(kline.open_time_ms ?? "", 10);
  if (Number.isFinite(openTimeMs)) {
    return openTimeMs;
  }
  const updatedAtMs = Number.parseInt(kline.updated_at_ms, 10);
  if (Number.isFinite(updatedAtMs)) {
    return updatedAtMs;
  }
  return 0;
}

function normalizeKlines(klines: Kline[]): CandleDatum[] {
  const parsed = klines
    .map((kline) => {
      const open = Number.parseFloat(kline.open);
      const high = Number.parseFloat(kline.high);
      const low = Number.parseFloat(kline.low);
      const close = Number.parseFloat(kline.close);
      const volume = Number.parseFloat(kline.volume);
      const timeMs = parseKlineTimeMs(kline);
      if (
        !Number.isFinite(open) ||
        !Number.isFinite(high) ||
        !Number.isFinite(low) ||
        !Number.isFinite(close) ||
        !Number.isFinite(volume) ||
        !Number.isFinite(timeMs)
      ) {
        return null;
      }

      return {
        time: Math.floor(timeMs / 1000) as UTCTimestamp,
        open,
        high,
        low,
        close,
        volume,
        timeMs,
      };
    })
    .filter((value): value is CandleDatum => value !== null)
    .sort((left, right) => left.timeMs - right.timeMs);

  const byTime = new Map<number, CandleDatum>();
  for (const candle of parsed) {
    byTime.set(candle.timeMs, candle);
  }

  return Array.from(byTime.values()).sort((left, right) => left.timeMs - right.timeMs);
}

function formatTimeLabel(time: Time): string {
  if (typeof time === "number") {
    return new Date(time * 1000).toLocaleTimeString();
  }
  if (typeof time === "string") {
    return new Date(time).toLocaleString();
  }
  const timestamp = new Date(Date.UTC(time.year, time.month - 1, time.day));
  return timestamp.toLocaleDateString();
}

export default function MarketCandlestickChart({
  chartKey,
  priceScaleMode,
  uiTheme,
  klines,
  loading,
  error,
  onNeedMoreHistory,
  canLoadMoreHistory = false,
  isLoadingMoreHistory = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const currentChartKeyRef = useRef(chartKey);
  const viewportByKeyRef = useRef<Record<string, LogicalRange | null | undefined>>({});
  const autoFittedKeyRef = useRef<Record<string, boolean>>({});
  const candleCountRef = useRef(0);
  const onNeedMoreHistoryRef = useRef<Props["onNeedMoreHistory"]>(onNeedMoreHistory);
  const canLoadMoreHistoryRef = useRef(canLoadMoreHistory);
  const isLoadingMoreHistoryRef = useRef(isLoadingMoreHistory);
  const lastMoreHistoryRequestMsRef = useRef(0);
  const [crosshairSnapshot, setCrosshairSnapshot] = useState<CrosshairSnapshot | null>(null);
  const isDarkTheme = uiTheme === "dark";

  const candleData = useMemo(() => normalizeKlines(klines), [klines]);
  useEffect(() => {
    candleCountRef.current = candleData.length;
  }, [candleData.length]);
  useEffect(() => {
    onNeedMoreHistoryRef.current = onNeedMoreHistory;
  }, [onNeedMoreHistory]);
  useEffect(() => {
    canLoadMoreHistoryRef.current = canLoadMoreHistory;
  }, [canLoadMoreHistory]);
  useEffect(() => {
    isLoadingMoreHistoryRef.current = isLoadingMoreHistory;
  }, [isLoadingMoreHistory]);
  const latestSnapshot = useMemo<CrosshairSnapshot | null>(() => {
    if (candleData.length === 0) {
      return null;
    }
    const last = candleData[candleData.length - 1];
    return {
      timeLabel: new Date(last.timeMs).toLocaleString(),
      open: last.open,
      high: last.high,
      low: last.low,
      close: last.close,
      volume: last.volume,
    };
  }, [candleData]);
  const statusSnapshot = crosshairSnapshot ?? latestSnapshot;
  const overlayMessage = useMemo(() => {
    if (loading) {
      return "Loading kline history...";
    }
    if (error) {
      return `History error: ${error}`;
    }
    if (candleData.length === 0) {
      return "Not enough points for candlestick chart yet.";
    }
    return null;
  }, [loading, error, candleData.length]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const chart = createChart(container, {
      width: Math.max(container.clientWidth, 320),
      height: 340,
      layout: {
        background: { color: "#ffffff" },
        textColor: "#475569",
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.18)" },
        horzLines: { color: "rgba(148, 163, 184, 0.18)" },
      },
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
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.6)",
      },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.6)",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 6,
      },
      crosshair: {
        vertLine: {
          color: "rgba(30, 41, 59, 0.35)",
          width: 1,
          labelVisible: true,
        },
        horzLine: {
          color: "rgba(30, 41, 59, 0.35)",
          width: 1,
          labelVisible: true,
        },
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#16a34a",
      downColor: "#e11d48",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#f43f5e",
      priceLineVisible: true,
      lastValueVisible: true,
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: "",
      priceFormat: {
        type: "volume",
      },
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.78,
        bottom: 0.0,
      },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    chart.subscribeCrosshairMove((param) => {
      const tooltip = tooltipRef.current;
      if (!tooltip) {
        return;
      }

      if (!param.point || !param.time || !candleSeriesRef.current || !volumeSeriesRef.current) {
        tooltip.style.display = "none";
        setCrosshairSnapshot(null);
        return;
      }

      const candle = param.seriesData.get(candleSeriesRef.current) as CandlestickData<Time> | undefined;
      const volume = param.seriesData.get(volumeSeriesRef.current) as HistogramData<Time> | undefined;
      if (!candle) {
        tooltip.style.display = "none";
        setCrosshairSnapshot(null);
        return;
      }

      const resolvedVolume = volume ? Number(volume.value) : null;

      tooltip.style.display = "block";
      tooltip.innerHTML = `
        <div><strong>${formatTimeLabel(param.time)}</strong></div>
        <div>O: ${Number(candle.open).toFixed(2)}</div>
        <div>H: ${Number(candle.high).toFixed(2)}</div>
        <div>L: ${Number(candle.low).toFixed(2)}</div>
        <div>C: ${Number(candle.close).toFixed(2)}</div>
        <div>V: ${resolvedVolume !== null ? resolvedVolume.toLocaleString() : "-"}</div>
      `;
      setCrosshairSnapshot({
        timeLabel: formatTimeLabel(param.time),
        open: Number(candle.open),
        high: Number(candle.high),
        low: Number(candle.low),
        close: Number(candle.close),
        volume: resolvedVolume,
      });

      const x = Math.max(8, Math.min(param.point.x + 14, container.clientWidth - 170));
      const y = Math.max(8, Math.min(param.point.y + 12, container.clientHeight - 120));
      tooltip.style.left = `${x}px`;
      tooltip.style.top = `${y}px`;
    });

    const handleRangeChange = (range: LogicalRange | null) => {
      viewportByKeyRef.current[currentChartKeyRef.current] = range;
      if (!range || !onNeedMoreHistoryRef.current || !canLoadMoreHistoryRef.current || isLoadingMoreHistoryRef.current) {
        return;
      }
      if (!candleSeriesRef.current) {
        return;
      }

      const barsInfo = candleSeriesRef.current.barsInLogicalRange(range);
      if (!barsInfo) {
        return;
      }

      const minBarsBeforeTrigger = Math.max(10, Math.floor(candleCountRef.current * 0.08));
      if (barsInfo.barsBefore >= minBarsBeforeTrigger) {
        return;
      }

      const now = Date.now();
      if (now - lastMoreHistoryRequestMsRef.current < 800) {
        return;
      }
      lastMoreHistoryRequestMsRef.current = now;
      onNeedMoreHistoryRef.current();
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(handleRangeChange);

    const resizeObserver = new ResizeObserver(() => {
      chart.applyOptions({
        width: container.clientWidth,
      });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleRangeChange);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current) {
      return;
    }
    chartRef.current.priceScale("right").applyOptions({
      mode: priceScaleMode === "log" ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal,
    });
  }, [priceScaleMode]);

  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current) {
      return;
    }

    chartRef.current.applyOptions({
      layout: {
        background: { color: isDarkTheme ? "#0f172a" : "#ffffff" },
        textColor: isDarkTheme ? "#94a3b8" : "#475569",
      },
      grid: {
        vertLines: { color: isDarkTheme ? "rgba(71, 85, 105, 0.26)" : "rgba(148, 163, 184, 0.18)" },
        horzLines: { color: isDarkTheme ? "rgba(71, 85, 105, 0.26)" : "rgba(148, 163, 184, 0.18)" },
      },
      rightPriceScale: {
        borderColor: isDarkTheme ? "rgba(71, 85, 105, 0.65)" : "rgba(148, 163, 184, 0.6)",
      },
      timeScale: {
        borderColor: isDarkTheme ? "rgba(71, 85, 105, 0.65)" : "rgba(148, 163, 184, 0.6)",
      },
      crosshair: {
        vertLine: {
          color: isDarkTheme ? "rgba(148, 163, 184, 0.35)" : "rgba(30, 41, 59, 0.35)",
          width: 1,
          labelVisible: true,
        },
        horzLine: {
          color: isDarkTheme ? "rgba(148, 163, 184, 0.35)" : "rgba(30, 41, 59, 0.35)",
          width: 1,
          labelVisible: true,
        },
      },
    });

    candleSeriesRef.current.applyOptions({
      upColor: isDarkTheme ? "#22c55e" : "#16a34a",
      downColor: isDarkTheme ? "#f43f5e" : "#e11d48",
      wickUpColor: isDarkTheme ? "#4ade80" : "#22c55e",
      wickDownColor: isDarkTheme ? "#fb7185" : "#f43f5e",
    });
  }, [isDarkTheme]);

  useEffect(() => {
    if (!chartRef.current) {
      return;
    }
    const timeScale = chartRef.current.timeScale();
    viewportByKeyRef.current[currentChartKeyRef.current] = timeScale.getVisibleLogicalRange();
    currentChartKeyRef.current = chartKey;

    const savedRange = viewportByKeyRef.current[chartKey];
    if (savedRange !== null && savedRange !== undefined) {
      timeScale.setVisibleLogicalRange(savedRange);
    }
  }, [chartKey]);

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) {
      return;
    }

    const candles: CandlestickData<Time>[] = candleData.map((item) => ({
      time: item.time,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    }));
    const volumes: HistogramData<Time>[] = candleData.map((item) => ({
      time: item.time,
      value: item.volume,
      color: item.close >= item.open ? (isDarkTheme ? "rgba(34, 197, 94, 0.45)" : "rgba(22, 163, 74, 0.42)") : isDarkTheme ? "rgba(244, 63, 94, 0.45)" : "rgba(225, 29, 72, 0.42)",
    }));

    candleSeriesRef.current.setData(candles);
    volumeSeriesRef.current.setData(volumes);

    if (chartRef.current && candles.length > 0) {
      const timeScale = chartRef.current.timeScale();
      const activeKey = currentChartKeyRef.current;
      const savedRange = viewportByKeyRef.current[activeKey];
      if (savedRange !== null && savedRange !== undefined) {
        timeScale.setVisibleLogicalRange(savedRange);
      } else if (!autoFittedKeyRef.current[activeKey]) {
        timeScale.fitContent();
        autoFittedKeyRef.current[activeKey] = true;
      }
    }
  }, [candleData, isDarkTheme]);

  return (
    <div className="tv-chart-wrapper">
      <div ref={containerRef} className="tv-chart-container" />
      <div ref={tooltipRef} className="tv-tooltip" style={{ display: "none" }} />
      {overlayMessage ? <div className="tv-overlay-message">{overlayMessage}</div> : null}
      <div className="tv-crosshair-bar">
        {statusSnapshot ? (
          <>
            <span>time: {statusSnapshot.timeLabel}</span>
            <span>O: {statusSnapshot.open.toFixed(2)}</span>
            <span>H: {statusSnapshot.high.toFixed(2)}</span>
            <span>L: {statusSnapshot.low.toFixed(2)}</span>
            <span>C: {statusSnapshot.close.toFixed(2)}</span>
            <span>V: {statusSnapshot.volume !== null ? statusSnapshot.volume.toLocaleString() : "-"}</span>
          </>
        ) : (
          <span>Move cursor over candles to inspect OHLCV.</span>
        )}
      </div>
    </div>
  );
}
