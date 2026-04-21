# ingester

Bybit + Binance websocket ingester:
- subscribes to ticker/trade/kline streams on both exchanges
- stores latest snapshots in Redis hashes:
  - `ticker:<source>:<SYMBOL>`
  - `trade:<source>:<SYMBOL>`
  - `kline:<source>:<SYMBOL>:<interval>`
- stores rolling kline history for charts:
  - `kline_history:<source>:<SYMBOL>:<interval>`
- publishes updates to channels:
  - `ticker_updates`
  - `trade_updates`
  - `kline_updates`.
