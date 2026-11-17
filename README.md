# CoinDCX Futures Trader — Paper Trading

A beginner-friendly **paper-trading-only** starter. It records simulated LONG/SHORT trades and tests stop-loss/take-profit outcomes. It does not connect to CoinDCX, TradingView, or any broker and cannot place real orders.

## Safety defaults
- Virtual starting balance: $1,000
- Risk budget: 1% of virtual balance per trade
- No exchange credentials or API keys
- No real order execution

## Requirements
Python 3.10+ (standard library only).

## Run locally
```bash
python app.py
```
The local server starts at `http://127.0.0.1:8000`.

## Create a simulated trade
```bash
curl -X POST http://127.0.0.1:8000/signal \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSDT","side":"LONG","entry":90000,"stop_loss":89500,"take_profit":91000}'
```

## Update prices and test exits
```bash
curl -X POST http://127.0.0.1:8000/mark \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSDT","price":91000}'
```
A simulated trade closes when the supplied mark price reaches its stop-loss or take-profit.

## Review journal and balance
- `GET /signals` — all recorded trades
- `GET /summary` — virtual balance and performance
- `GET /health` — service status

## Important limitations
This is a local prototype, not a hosted webhook. It does not fetch live prices, receive TradingView alerts automatically, model fees/slippage/funding, or guarantee realistic fills. A mark price must be supplied manually. Do not expose this development server publicly. Validate strategy performance with historical data and realistic costs before considering any live integration.
