"use client";

import MarketCandlestickChart from "./components/MarketCandlestickChart";
import { useEffect, useMemo, useRef, useState } from "react";

type StreamStatus = "connecting" | "connected" | "disconnected";
type StreamName = "tickers" | "trades" | "klines" | "orderbooks";

type Ticker = {
  symbol: string;
  price: string;
  change24h: string;
  volume24h: string;
  source: string;
  updated_at_ms: string;
};

type Trade = {
  symbol: string;
  price: string;
  size: string;
  side: string;
  source: string;
  updated_at_ms: string;
};

type Kline = {
  symbol: string;
  interval: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  source: string;
  updated_at_ms: string;
  open_time_ms?: string;
};

type OrderbookSnapshot = {
  symbol: string;
  source: string;
  bids_json: string;
  asks_json: string;
  updated_at_ms: string;
};

type OrderbookLevel = {
  price: number;
  size: number;
  total: number;
};

type SourceSymbol = { symbol: string; source: string };
type UiTheme = "light" | "dark";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TICKERS_API_URL = `${API_BASE_URL}/api/tickers`;
const TRADES_API_URL = `${API_BASE_URL}/api/trades`;
const KLINES_API_URL = `${API_BASE_URL}/api/klines`;
const KLINE_HISTORY_API_URL = `${API_BASE_URL}/api/klines/history`;
const ORDERBOOKS_API_URL = `${API_BASE_URL}/api/orderbooks`;
const WS_TICKERS_URL =
  process.env.NEXT_PUBLIC_WS_TICKERS_URL ?? process.env.NEXT_PUBLIC_WS_BASE_URL ?? "ws://localhost:8000/ws/tickers";
const WS_TRADES_URL = process.env.NEXT_PUBLIC_WS_TRADES_URL ?? "ws://localhost:8000/ws/trades";
const WS_KLINES_URL = process.env.NEXT_PUBLIC_WS_KLINES_URL ?? "ws://localhost:8000/ws/klines";
const WS_ORDERBOOKS_URL = process.env.NEXT_PUBLIC_WS_ORDERBOOKS_URL ?? "ws://localhost:8000/ws/orderbooks";
const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 10000;
const KLINE_HISTORY_LIMIT = 120;
const KLINE_HISTORY_POLL_INTERVAL_MS = 1000;
const ORDERBOOK_ROWS_LIMIT = 10;
const ORDERBOOK_RATIO_LEVELS = 20;
const TIMEFRAME_OPTIONS = ["1m", "5m", "15m", "1h"] as const;
const PRICE_SCALE_OPTIONS = ["linear", "log"] as const;

type IconProps = { className?: string };

function PulseIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M3 12h4l2.4-4.5L13 17l2.2-5H21"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ActivityIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M4 12h3l2-4 4 8 2-4h5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function LayersIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="m12 4 8 4.5-8 4.5-8-4.5L12 4Zm8 8-8 4.5L4 12m16 4-8 4.5L4 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CandlesIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 5v14M7 9h3v6H7M14 3v18M14 7h3v10h-3" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function BookIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21V5.5Zm0 0A2.5 2.5 0 0 1 6.5 8H20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SunIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoonIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M20 14.2A8.2 8.2 0 1 1 9.8 4a7 7 0 1 0 10.2 10.2Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function sortBySymbol<T extends SourceSymbol>(items: T[]): T[] {
  return [...items].sort((left, right) => {
    const symbolDiff = left.symbol.localeCompare(right.symbol);
    if (symbolDiff !== 0) {
      return symbolDiff;
    }
    return left.source.localeCompare(right.source);
  });
}

function tickerKey(ticker: Ticker): string {
  return `${ticker.source}:${ticker.symbol}`;
}

function tradeKey(trade: Trade): string {
  return `${trade.source}:${trade.symbol}`;
}

function klineKey(kline: Kline): string {
  return `${kline.source}:${kline.symbol}:${kline.interval}`;
}

function orderbookKey(orderbook: Pick<OrderbookSnapshot, "source" | "symbol">): string {
  return `${orderbook.source}:${orderbook.symbol}`;
}

function sourceSymbolKey(value: SourceSymbol): string {
  return `${value.source}:${value.symbol}`;
}

function klineTimeMs(kline: Kline): number {
  const openTime = Number.parseInt(kline.open_time_ms ?? "", 10);
  if (Number.isFinite(openTime)) {
    return openTime;
  }
  const updatedAt = Number.parseInt(kline.updated_at_ms, 10);
  if (Number.isFinite(updatedAt)) {
    return updatedAt;
  }
  return 0;
}

function isTickerPayload(payload: unknown): payload is Ticker {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  const candidate = payload as Record<string, unknown>;
  return (
    typeof candidate.symbol === "string" &&
    typeof candidate.price === "string" &&
    typeof candidate.change24h === "string" &&
    typeof candidate.volume24h === "string" &&
    typeof candidate.source === "string" &&
    typeof candidate.updated_at_ms === "string"
  );
}

function isTradePayload(payload: unknown): payload is Trade {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  const candidate = payload as Record<string, unknown>;
  return (
    typeof candidate.symbol === "string" &&
    typeof candidate.price === "string" &&
    typeof candidate.size === "string" &&
    typeof candidate.side === "string" &&
    typeof candidate.source === "string" &&
    typeof candidate.updated_at_ms === "string"
  );
}

function isKlinePayload(payload: unknown): payload is Kline {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  const candidate = payload as Record<string, unknown>;
  return (
    typeof candidate.symbol === "string" &&
    typeof candidate.interval === "string" &&
    typeof candidate.open === "string" &&
    typeof candidate.high === "string" &&
    typeof candidate.low === "string" &&
    typeof candidate.close === "string" &&
    typeof candidate.volume === "string" &&
    typeof candidate.source === "string" &&
    typeof candidate.updated_at_ms === "string" &&
    (candidate.open_time_ms === undefined || typeof candidate.open_time_ms === "string")
  );
}

function isOrderbookPayload(payload: unknown): payload is OrderbookSnapshot {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  const candidate = payload as Record<string, unknown>;
  return (
    typeof candidate.symbol === "string" &&
    typeof candidate.source === "string" &&
    typeof candidate.bids_json === "string" &&
    typeof candidate.asks_json === "string" &&
    typeof candidate.updated_at_ms === "string"
  );
}

function parseOrderbookSide(raw: string, direction: "asc" | "desc", limit: number): OrderbookLevel[] {
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    const levels = parsed
      .map((item) => {
        if (!Array.isArray(item) || item.length < 2) {
          return null;
        }
        const price = Number.parseFloat(String(item[0]));
        const size = Number.parseFloat(String(item[1]));
        if (!Number.isFinite(price) || !Number.isFinite(size) || price <= 0 || size < 0) {
          return null;
        }
        return { price, size };
      })
      .filter((item): item is { price: number; size: number } => item !== null)
      .sort((left, right) => (direction === "asc" ? left.price - right.price : right.price - left.price))
      .slice(0, Math.max(limit, 1));

    let runningTotal = 0;
    return levels.map((item) => {
      runningTotal += item.size;
      return { ...item, total: runningTotal };
    });
  } catch {
    return [];
  }
}

function isHeartbeatPayload(payload: unknown): payload is { type: "heartbeat" } {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  return (payload as { type?: string }).type === "heartbeat";
}

function useRealtimeStream<T extends object>(
  url: string,
  streamName: StreamName,
  validatePayload: (payload: unknown) => payload is T,
  onPayload: (payload: T) => void,
  setStreamStatus: React.Dispatch<React.SetStateAction<Record<StreamName, StreamStatus>>>,
) {
  const onPayloadRef = useRef(onPayload);
  useEffect(() => {
    onPayloadRef.current = onPayload;
  }, [onPayload]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempt = 0;
    let stopped = false;

    function scheduleReconnect() {
      if (stopped || reconnectTimer !== null) {
        return;
      }
      const delay = Math.min(RECONNECT_BASE_DELAY_MS * 2 ** reconnectAttempt, RECONNECT_MAX_DELAY_MS);
      reconnectAttempt += 1;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (!stopped) {
          setStreamStatus((previous) => ({ ...previous, [streamName]: "connecting" }));
          connect();
        }
      }, delay);
    }

    function connect() {
      socket = new WebSocket(url);
      socket.onopen = () => {
        reconnectAttempt = 0;
        setStreamStatus((previous) => ({ ...previous, [streamName]: "connected" }));
      };
      socket.onerror = () => {
        socket?.close();
      };
      socket.onclose = () => {
        if (!stopped) {
          setStreamStatus((previous) => ({ ...previous, [streamName]: "disconnected" }));
          scheduleReconnect();
        }
      };
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as unknown;
          if (isHeartbeatPayload(payload) || !validatePayload(payload)) {
            return;
          }
          onPayloadRef.current(payload);
        } catch {
          // Ignore malformed stream messages.
        }
      };
    }

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [setStreamStatus, streamName, url, validatePayload]);
}

export default function HomePage() {
  const [uiTheme, setUiTheme] = useState<UiTheme>("light");
  const [tickersByKey, setTickersByKey] = useState<Record<string, Ticker>>({});
  const [tradesByKey, setTradesByKey] = useState<Record<string, Trade>>({});
  const [klinesByKey, setKlinesByKey] = useState<Record<string, Kline>>({});
  const [orderbooksByKey, setOrderbooksByKey] = useState<Record<string, OrderbookSnapshot>>({});
  const [selectedTimeframe, setSelectedTimeframe] = useState<(typeof TIMEFRAME_OPTIONS)[number]>("1m");
  const [selectedPriceScaleMode, setSelectedPriceScaleMode] = useState<(typeof PRICE_SCALE_OPTIONS)[number]>("linear");
  const [selectedPairKey, setSelectedPairKey] = useState<string>("");
  const [klineHistory, setKlineHistory] = useState<Kline[]>([]);
  const [isKlineHistoryLoading, setIsKlineHistoryLoading] = useState(false);
  const [klineHistoryError, setKlineHistoryError] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState<Record<StreamName, StreamStatus>>({
    tickers: "connecting",
    trades: "connecting",
    klines: "connecting",
    orderbooks: "connecting",
  });

  useEffect(() => {
    async function loadInitialData() {
      try {
        const [tickersResponse, tradesResponse, klinesResponse, orderbooksResponse] = await Promise.all([
          fetch(TICKERS_API_URL),
          fetch(TRADES_API_URL),
          fetch(KLINES_API_URL),
          fetch(ORDERBOOKS_API_URL),
        ]);

        if (tickersResponse.ok) {
          const payload = (await tickersResponse.json()) as Ticker[];
          setTickersByKey(Object.fromEntries(payload.map((ticker) => [tickerKey(ticker), ticker])));
        }
        if (tradesResponse.ok) {
          const payload = (await tradesResponse.json()) as Trade[];
          setTradesByKey(Object.fromEntries(payload.map((trade) => [tradeKey(trade), trade])));
        }
        if (klinesResponse.ok) {
          const payload = (await klinesResponse.json()) as Kline[];
          setKlinesByKey(Object.fromEntries(payload.map((kline) => [klineKey(kline), kline])));
        }
        if (orderbooksResponse.ok) {
          const payload = (await orderbooksResponse.json()) as OrderbookSnapshot[];
          setOrderbooksByKey(Object.fromEntries(payload.map((item) => [orderbookKey(item), item])));
        }
      } catch {
        // Ignore startup fetch errors because WS streams can recover state.
      }
    }

    loadInitialData().catch(() => undefined);
  }, []);

  useRealtimeStream(
    WS_TICKERS_URL,
    "tickers",
    isTickerPayload,
    (payload) => setTickersByKey((previous) => ({ ...previous, [tickerKey(payload)]: payload })),
    setStreamStatus,
  );
  useRealtimeStream(
    WS_TRADES_URL,
    "trades",
    isTradePayload,
    (payload) => setTradesByKey((previous) => ({ ...previous, [tradeKey(payload)]: payload })),
    setStreamStatus,
  );
  useRealtimeStream(
    WS_KLINES_URL,
    "klines",
    isKlinePayload,
    (payload) => setKlinesByKey((previous) => ({ ...previous, [klineKey(payload)]: payload })),
    setStreamStatus,
  );
  useRealtimeStream(
    WS_ORDERBOOKS_URL,
    "orderbooks",
    isOrderbookPayload,
    (payload) => setOrderbooksByKey((previous) => ({ ...previous, [orderbookKey(payload)]: payload })),
    setStreamStatus,
  );

  const sortedTickers = useMemo(() => sortBySymbol(Object.values(tickersByKey)), [tickersByKey]);
  const sortedTrades = useMemo(() => sortBySymbol(Object.values(tradesByKey)), [tradesByKey]);
  const sortedKlines = useMemo(() => sortBySymbol(Object.values(klinesByKey)), [klinesByKey]);
  const timeframeKlines = useMemo(
    () => sortedKlines.filter((kline) => kline.interval === selectedTimeframe),
    [selectedTimeframe, sortedKlines],
  );

  const pairOptions = useMemo(() => {
    const map = new Map<string, SourceSymbol>();
    for (const kline of timeframeKlines) {
      map.set(sourceSymbolKey(kline), { source: kline.source, symbol: kline.symbol });
    }
    return sortBySymbol(Array.from(map.values()));
  }, [timeframeKlines]);

  const effectiveSelectedPairKey = useMemo(() => {
    if (pairOptions.length === 0) {
      return "";
    }
    if (selectedPairKey && pairOptions.some((pair) => sourceSymbolKey(pair) === selectedPairKey)) {
      return selectedPairKey;
    }
    return sourceSymbolKey(pairOptions[0]);
  }, [pairOptions, selectedPairKey]);

  const selectedPair = useMemo(() => {
    if (!effectiveSelectedPairKey) {
      return null;
    }
    const [source, symbol] = effectiveSelectedPairKey.split(":");
    if (!source || !symbol) {
      return null;
    }
    return { source, symbol };
  }, [effectiveSelectedPairKey]);

  const selectedOrderbook = useMemo(() => {
    if (!selectedPair) {
      return null;
    }
    return orderbooksByKey[sourceSymbolKey(selectedPair)] ?? null;
  }, [orderbooksByKey, selectedPair]);
  const selectedTrade = useMemo(() => {
    if (!selectedPair) {
      return null;
    }
    return tradesByKey[sourceSymbolKey(selectedPair)] ?? null;
  }, [selectedPair, tradesByKey]);

  const orderbookBidsTop20 = useMemo(
    () => (selectedOrderbook ? parseOrderbookSide(selectedOrderbook.bids_json, "desc", ORDERBOOK_RATIO_LEVELS) : []),
    [selectedOrderbook],
  );
  const orderbookAsksTop20 = useMemo(
    () => (selectedOrderbook ? parseOrderbookSide(selectedOrderbook.asks_json, "asc", ORDERBOOK_RATIO_LEVELS) : []),
    [selectedOrderbook],
  );
  const orderbookBids = useMemo(() => orderbookBidsTop20.slice(0, ORDERBOOK_ROWS_LIMIT), [orderbookBidsTop20]);
  const orderbookAsks = useMemo(() => orderbookAsksTop20.slice(0, ORDERBOOK_ROWS_LIMIT), [orderbookAsksTop20]);
  const bestBid = useMemo(() => (orderbookBids.length > 0 ? orderbookBids[0].price : null), [orderbookBids]);
  const bestAsk = useMemo(() => (orderbookAsks.length > 0 ? orderbookAsks[0].price : null), [orderbookAsks]);
  const spread = useMemo(
    () => (bestBid !== null && bestAsk !== null ? Math.max(0, bestAsk - bestBid) : null),
    [bestAsk, bestBid],
  );
  const maxOrderbookTotal = useMemo(() => {
    const totals = [...orderbookBids.map((level) => level.total), ...orderbookAsks.map((level) => level.total)];
    if (totals.length === 0) {
      return 1;
    }
    return Math.max(...totals, 1);
  }, [orderbookAsks, orderbookBids]);
  const orderbookBidSizeTop20 = useMemo(
    () => orderbookBidsTop20.reduce((acc, level) => acc + level.size, 0),
    [orderbookBidsTop20],
  );
  const orderbookAskSizeTop20 = useMemo(
    () => orderbookAsksTop20.reduce((acc, level) => acc + level.size, 0),
    [orderbookAsksTop20],
  );
  const orderbookTotalTop20 = useMemo(() => orderbookBidSizeTop20 + orderbookAskSizeTop20, [orderbookAskSizeTop20, orderbookBidSizeTop20]);
  const orderbookBidPct = useMemo(
    () => (orderbookTotalTop20 > 0 ? (orderbookBidSizeTop20 / orderbookTotalTop20) * 100 : 50),
    [orderbookBidSizeTop20, orderbookTotalTop20],
  );
  const orderbookAskPct = useMemo(
    () => (orderbookTotalTop20 > 0 ? (orderbookAskSizeTop20 / orderbookTotalTop20) * 100 : 50),
    [orderbookAskSizeTop20, orderbookTotalTop20],
  );

  useEffect(() => {
    setSelectedPairKey("");
  }, [selectedTimeframe]);

  const selectedHistoryParams = useMemo(() => {
    if (!selectedPair) {
      return null;
    }
    return {
      source: selectedPair.source,
      symbol: selectedPair.symbol,
      interval: selectedTimeframe,
    };
  }, [selectedPair, selectedTimeframe]);

  useEffect(() => {
    if (!selectedHistoryParams) {
      setKlineHistory([]);
      setKlineHistoryError(null);
      setIsKlineHistoryLoading(false);
      return;
    }

    const { source, symbol, interval } = selectedHistoryParams;
    let cancelled = false;
    let firstLoad = true;

    async function loadHistory() {
      try {
        if (firstLoad) {
          setIsKlineHistoryLoading(true);
        }
        const params = new URLSearchParams({
          source,
          symbol,
          interval,
          limit: String(KLINE_HISTORY_LIMIT),
        });
        const response = await fetch(`${KLINE_HISTORY_API_URL}?${params.toString()}`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = (await response.json()) as unknown;
        if (!Array.isArray(payload)) {
          throw new Error("Invalid history payload");
        }
        const items = payload.filter(isKlinePayload).sort((left, right) => klineTimeMs(left) - klineTimeMs(right));
        if (!cancelled) {
          setKlineHistory(items);
          setKlineHistoryError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setKlineHistoryError(error instanceof Error ? error.message : "Failed to load kline history");
        }
      } finally {
        if (!cancelled && firstLoad) {
          setIsKlineHistoryLoading(false);
        }
        firstLoad = false;
      }
    }

    loadHistory().catch(() => undefined);
    const intervalId = setInterval(() => {
      loadHistory().catch(() => undefined);
    }, KLINE_HISTORY_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [selectedHistoryParams]);

  const chartMin = useMemo(() => {
    const values = klineHistory.map((kline) => Number.parseFloat(kline.low)).filter(Number.isFinite);
    if (values.length === 0) {
      return null;
    }
    return Math.min(...values);
  }, [klineHistory]);

  const chartMax = useMemo(() => {
    const values = klineHistory.map((kline) => Number.parseFloat(kline.high)).filter(Number.isFinite);
    if (values.length === 0) {
      return null;
    }
    return Math.max(...values);
  }, [klineHistory]);

  const latestClose = useMemo(() => {
    if (klineHistory.length === 0) {
      return null;
    }
    const parsed = Number.parseFloat(klineHistory[klineHistory.length - 1].close);
    return Number.isFinite(parsed) ? parsed : null;
  }, [klineHistory]);

  const firstTimeLabel = useMemo(() => {
    if (klineHistory.length === 0) {
      return "";
    }
    return new Date(klineTimeMs(klineHistory[0])).toLocaleTimeString();
  }, [klineHistory]);

  const lastTimeLabel = useMemo(() => {
    if (klineHistory.length === 0) {
      return "";
    }
    return new Date(klineTimeMs(klineHistory[klineHistory.length - 1])).toLocaleTimeString();
  }, [klineHistory]);

  const tickerState =
    sortedTickers.length > 0 ? "ready" : streamStatus.tickers === "connecting" ? "loading" : streamStatus.tickers === "disconnected" ? "error" : "empty";
  const tradeState =
    sortedTrades.length > 0 ? "ready" : streamStatus.trades === "connecting" ? "loading" : streamStatus.trades === "disconnected" ? "error" : "empty";
  const klineState =
    timeframeKlines.length > 0 ? "ready" : streamStatus.klines === "connecting" ? "loading" : streamStatus.klines === "disconnected" ? "error" : "empty";

  const connectedStreams = Object.values(streamStatus).filter((status) => status === "connected").length;
  const connectionRatio = `${connectedStreams}/${Object.keys(streamStatus).length}`;
  const tickerTape = useMemo(
    () =>
      sortedTickers
        .slice(0, 10)
        .map((ticker) => {
          const price = Number.parseFloat(ticker.price);
          const change = Number.parseFloat(ticker.change24h) * 100;
          return `${ticker.symbol} ${Number.isFinite(price) ? price.toFixed(2) : "-"} (${Number.isFinite(change) ? change.toFixed(2) : "-"}%)`;
        })
        .join("  •  "),
    [sortedTickers],
  );

  useEffect(() => {
    const storedTheme = window.localStorage.getItem("ui-theme");
    if (storedTheme === "light" || storedTheme === "dark") {
      setUiTheme(storedTheme);
      return;
    }
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    setUiTheme(prefersDark ? "dark" : "light");
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = uiTheme;
    document.documentElement.style.colorScheme = uiTheme;
    window.localStorage.setItem("ui-theme", uiTheme);
  }, [uiTheme]);

  return (
    <main className="dashboard-shell">
      <header className="hero">
        <div>
          <p className="hero-kicker">Live Market Console</p>
          <h1 className="hero-title">Realtime Trading Dashboard</h1>
          <p className="hero-subtitle">
            Multi-stream observability for tickers, trades, klines and orderbook depth. Designed for quick anomaly detection and pair inspection.
          </p>
        </div>
        <div className="hero-stats">
          <div className="theme-control">
            <button
              type="button"
              className="theme-toggle theme-toggle-icon"
              onClick={() => setUiTheme((prev) => (prev === "light" ? "dark" : "light"))}
              aria-pressed={uiTheme === "dark"}
              aria-label="Toggle dark or light mode"
              title={uiTheme === "light" ? "Switch to dark theme" : "Switch to light theme"}
            >
              {uiTheme === "light" ? <MoonIcon className="theme-icon" /> : <SunIcon className="theme-icon" />}
            </button>
          </div>
          <div className="hero-stat hero-stat-inline">
            <span className="hero-stat-label">
              <PulseIcon className="label-icon" />
              Streams online
            </span>
            <span className="hero-stat-value">{connectionRatio}</span>
          </div>
        </div>
      </header>

      <section className="market-grid">
        <article className="market-panel market-panel-tape">
          <div className="market-panel-head">
            <h2 className="title-with-icon">
              <PulseIcon className="title-icon" />
              Realtime Tape
            </h2>
          </div>
          <div className="tape">
            <p>{tickerTape || "Waiting for ticker stream..."}</p>
            <p aria-hidden="true">{tickerTape || "Waiting for ticker stream..."}</p>
          </div>
        </article>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <h2 className="title-with-icon">
            <LayersIcon className="title-icon" />
            Ticker Snapshot
          </h2>
          <div className="status-group">
            <span className={`status status-${streamStatus.tickers}`}>tickers: {streamStatus.tickers}</span>
            <span className={`status status-${streamStatus.trades}`}>trades: {streamStatus.trades}</span>
            <span className={`status status-${streamStatus.klines}`}>klines: {streamStatus.klines}</span>
            <span className={`status status-${streamStatus.orderbooks}`}>orderbooks: {streamStatus.orderbooks}</span>
          </div>
        </div>
        <div className="cards">
          {tickerState === "loading" &&
            Array.from({ length: 6 }).map((_, index) => (
              <article className="card skeleton-card" key={`ticker-skeleton-${index}`}>
                <span className="skeleton-line skeleton-title" />
                <span className="skeleton-line skeleton-value" />
                <span className="skeleton-line" />
                <span className="skeleton-line skeleton-small" />
              </article>
            ))}
          {tickerState === "error" && <p className="empty error">Ticker stream disconnected. Waiting for reconnect...</p>}
          {tickerState === "empty" && <p className="empty">No ticker data yet.</p>}
          {tickerState === "ready" &&
          sortedTickers.map((ticker, index) => {
            const change = Number.parseFloat(ticker.change24h) * 100;
            const isPositive = change >= 0;
            return (
              <article className="card bento-card" key={tickerKey(ticker)} style={{ "--index": String(index) } as React.CSSProperties}>
                <div className="card-top">
                  <h2>{ticker.symbol}</h2>
                  <span className={isPositive ? "badge badge-up" : "badge badge-down"}>{change.toFixed(2)}%</span>
                </div>
                <p className="price">${Number.parseFloat(ticker.price).toLocaleString()}</p>
                <p className="meta">24h volume: {Number.parseFloat(ticker.volume24h).toLocaleString()}</p>
                <p className="meta">
                  source: {ticker.source.toUpperCase()} | updated:{" "}
                  {new Date(Number(ticker.updated_at_ms)).toLocaleTimeString()}
                </p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <h2 className="title-with-icon">
            <ActivityIcon className="title-icon" />
            Latest Trade Snapshots
          </h2>
        </div>
        <div className="cards">
          {tradeState === "loading" &&
            Array.from({ length: 4 }).map((_, index) => (
              <article className="card skeleton-card" key={`trade-skeleton-${index}`}>
                <span className="skeleton-line skeleton-title" />
                <span className="skeleton-line skeleton-value" />
                <span className="skeleton-line" />
                <span className="skeleton-line skeleton-small" />
              </article>
            ))}
          {tradeState === "error" && <p className="empty error">Trade stream disconnected. Waiting for reconnect...</p>}
          {tradeState === "empty" && <p className="empty">No trade data yet.</p>}
          {tradeState === "ready" &&
          sortedTrades.map((trade, index) => {
            const side = trade.side.toLowerCase();
            const isBuy = side === "buy";
            const isSell = side === "sell";
            return (
              <article className="card bento-card" key={tradeKey(trade)} style={{ "--index": String(index) } as React.CSSProperties}>
                <div className="card-top">
                  <h2>{trade.symbol}</h2>
                  <span className={isBuy ? "badge badge-up" : isSell ? "badge badge-down" : "badge"}>
                    {isBuy ? "BUY" : isSell ? "SELL" : "N/A"}
                  </span>
                </div>
                <p className="price">${Number.parseFloat(trade.price).toLocaleString()}</p>
                <p className="meta">size: {Number.parseFloat(trade.size).toLocaleString()}</p>
                <p className="meta">
                  source: {trade.source.toUpperCase()} | updated:{" "}
                  {new Date(Number(trade.updated_at_ms)).toLocaleTimeString()}
                </p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <h2 className="title-with-icon">
            <CandlesIcon className="title-icon" />
            Latest Klines
          </h2>
        </div>
        <div className="cards">
          {klineState === "loading" &&
            Array.from({ length: 4 }).map((_, index) => (
              <article className="card skeleton-card" key={`kline-skeleton-${index}`}>
                <span className="skeleton-line skeleton-title" />
                <span className="skeleton-line" />
                <span className="skeleton-line" />
                <span className="skeleton-line skeleton-small" />
              </article>
            ))}
          {klineState === "error" && <p className="empty error">Kline stream disconnected. Waiting for reconnect...</p>}
          {klineState === "empty" && <p className="empty">No kline data yet.</p>}
          {klineState === "ready" &&
          timeframeKlines.map((kline, index) => (
            <article className="card bento-card" key={klineKey(kline)} style={{ "--index": String(index) } as React.CSSProperties}>
              <div className="card-top">
                <h2>{kline.symbol}</h2>
                <span className="badge">{kline.interval}</span>
              </div>
              <p className="meta">
                O/H/L/C: {kline.open} / {kline.high} / {kline.low} / {kline.close}
              </p>
              <p className="meta">volume: {Number.parseFloat(kline.volume).toLocaleString()}</p>
              <p className="meta">
                source: {kline.source.toUpperCase()} | updated:{" "}
                {new Date(Number(kline.updated_at_ms)).toLocaleTimeString()}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-block chart-section">
        <div className="section-heading">
          <h2 className="title-with-icon">
            <CandlesIcon className="title-icon" />
            Kline Candlestick Chart
          </h2>
        </div>
        <div className="chart-controls">
          <label className="chart-label" htmlFor="timeframe-selector">
            Timeframe
          </label>
          <select
            id="timeframe-selector"
            className="chart-select"
            value={selectedTimeframe}
            onChange={(event) => setSelectedTimeframe(event.target.value as (typeof TIMEFRAME_OPTIONS)[number])}
          >
            {TIMEFRAME_OPTIONS.map((interval) => (
              <option key={interval} value={interval}>
                {interval}
              </option>
            ))}
          </select>

          <label className="chart-label" htmlFor="kline-selector">
            Pair
          </label>
          <select
            id="kline-selector"
            className="chart-select"
            value={effectiveSelectedPairKey}
            onChange={(event) => setSelectedPairKey(event.target.value)}
            disabled={pairOptions.length === 0}
          >
            {pairOptions.map((pair) => (
              <option key={sourceSymbolKey(pair)} value={sourceSymbolKey(pair)}>
                {pair.symbol} | {pair.source.toUpperCase()}
              </option>
            ))}
          </select>

          <label className="chart-label" htmlFor="price-scale-selector">
            Price scale
          </label>
          <select
            id="price-scale-selector"
            className="chart-select"
            value={selectedPriceScaleMode}
            onChange={(event) =>
              setSelectedPriceScaleMode(event.target.value as (typeof PRICE_SCALE_OPTIONS)[number])
            }
          >
            {PRICE_SCALE_OPTIONS.map((mode) => (
              <option key={mode} value={mode}>
                {mode === "linear" ? "Linear" : "Log"}
              </option>
            ))}
          </select>
        </div>

        {selectedPair === null ? (
          <p className="chart-empty">No kline source is available yet.</p>
        ) : (
          <div className="chart-layout">
            <div className="chart-main">
              <MarketCandlestickChart
                chartKey={`${selectedPair.source}:${selectedPair.symbol}:${selectedTimeframe}`}
                priceScaleMode={selectedPriceScaleMode}
                uiTheme={uiTheme}
                klines={klineHistory}
                loading={isKlineHistoryLoading}
                error={klineHistoryError}
              />
              <div className="chart-meta">
                <span>
                  low/high min/max: {chartMin?.toFixed(2)} / {chartMax?.toFixed(2)}
                </span>
                <span>latest close: {latestClose?.toFixed(2)}</span>
                <span>Y axis: price</span>
                <span>X axis: time</span>
                <span>
                  range: {firstTimeLabel} - {lastTimeLabel}
                </span>
              </div>
            </div>

            <aside className="orderbook-panel">
              <div className="orderbook-header">
                <h3>
                  <BookIcon className="title-icon orderbook-title-icon" />
                  Order Book ({selectedPair.symbol} | {selectedPair.source.toUpperCase()})
                </h3>
                <span className={`status status-${streamStatus.orderbooks}`}>{streamStatus.orderbooks}</span>
              </div>
              {selectedOrderbook === null ? (
                <p className="chart-empty">Order book snapshot is not available yet.</p>
              ) : (
                <>
                  <div className="orderbook-spread">
                    <span>best bid: {bestBid?.toFixed(4) ?? "-"}</span>
                    <span>best ask: {bestAsk?.toFixed(4) ?? "-"}</span>
                    <span>spread: {spread?.toFixed(4) ?? "-"}</span>
                  </div>

                  <div className="orderbook-section">
                    <p className="orderbook-title orderbook-title-asks">Asks</p>
                    <div className="orderbook-columns">
                      <span className="orderbook-col-price">price</span>
                      <span className="orderbook-col-size">size</span>
                      <span className="orderbook-col-total">total</span>
                    </div>
                    {orderbookAsks
                      .slice()
                      .reverse()
                      .map((level) => (
                        <div
                          className="orderbook-row orderbook-row-ask"
                          key={`ask-${level.price}-${level.total}`}
                          style={{ "--orderbook-depth": `${(level.total / maxOrderbookTotal) * 100}%` } as React.CSSProperties}
                        >
                          <span className="orderbook-price orderbook-col-price">{level.price.toFixed(2)}</span>
                          <span className="orderbook-col-size">{level.size.toFixed(4)}</span>
                          <span className="orderbook-col-total">{level.total.toFixed(4)}</span>
                        </div>
                      ))}
                  </div>

                  <div className="orderbook-last-trade">
                    <span
                      className={
                        selectedTrade?.side.toLowerCase() === "buy"
                          ? "orderbook-last-side orderbook-last-side-buy"
                          : selectedTrade?.side.toLowerCase() === "sell"
                            ? "orderbook-last-side orderbook-last-side-sell"
                            : "orderbook-last-side"
                      }
                    >
                      {selectedTrade?.side ? selectedTrade.side.toUpperCase() : "N/A"}
                    </span>
                    <span className="orderbook-last-price">
                      {selectedTrade ? Number.parseFloat(selectedTrade.price).toFixed(2) : "-"}
                    </span>
                    <span className="orderbook-last-updated">
                      {selectedTrade ? new Date(Number(selectedTrade.updated_at_ms)).toLocaleTimeString() : ""}
                    </span>
                  </div>

                  <div className="orderbook-section">
                    <p className="orderbook-title orderbook-title-bids">Bids</p>
                    <div className="orderbook-columns">
                      <span className="orderbook-col-price">price</span>
                      <span className="orderbook-col-size">size</span>
                      <span className="orderbook-col-total">total</span>
                    </div>
                    {orderbookBids.map((level) => (
                      <div
                        className="orderbook-row orderbook-row-bid"
                        key={`bid-${level.price}-${level.total}`}
                        style={{ "--orderbook-depth": `${(level.total / maxOrderbookTotal) * 100}%` } as React.CSSProperties}
                      >
                        <span className="orderbook-price orderbook-col-price">{level.price.toFixed(2)}</span>
                        <span className="orderbook-col-size">{level.size.toFixed(4)}</span>
                        <span className="orderbook-col-total">{level.total.toFixed(4)}</span>
                      </div>
                    ))}
                  </div>

                  <div className="orderbook-balance">
                    <p className="orderbook-balance-title">Top-20 depth: bids vs asks</p>
                    <div className="orderbook-balance-bar">
                      <span className="orderbook-balance-part orderbook-balance-part-bid" style={{ width: `${orderbookBidPct}%` }}>
                        B {orderbookBidPct.toFixed(0)}%
                      </span>
                      <span className="orderbook-balance-part orderbook-balance-part-ask" style={{ width: `${orderbookAskPct}%` }}>
                        {orderbookAskPct.toFixed(0)}% S
                      </span>
                    </div>
                  </div>
                  <p className="meta">updated: {new Date(Number(selectedOrderbook.updated_at_ms)).toLocaleTimeString()}</p>
                </>
              )}
            </aside>
          </div>
        )}
      </section>
    </main>
  );
}
