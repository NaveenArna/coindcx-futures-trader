# CoinDCX Futures Trader — Paper Trading

A beginner-friendly **paper-trading-only** starter. It records simulated LONG/SHORT trades and tests stop-loss/take-profit outcomes. It does not connect to CoinDCX, TradingView, or any broker and cannot place real orders.

## Mobile dashboard
The app includes a responsive dashboard in `dashboard.html`. When the Python server is running, open `http://127.0.0.1:8000/` in a browser on the same device/network as the server. The dashboard lets you:
- Record simulated LONG or SHORT trades with entry, stop-loss and take-profit.
- Review open and closed trades, virtual balance and realized P&L.
- Enter a test/mark price to check whether open trades reach SL or TP.

## Safety defaults
- Virtual starting balance: $1,000
- Fixed risk budget: $10 per trade (1% of the starting balance)
- No exchange credentials or API keys
- No real order execution

## Requirements
Python 3.10+ (standard library only).

## Run locally
```bash
python app.py
```
The local server starts at `http://127.0.0.1:8000`. The dashboard is served at the root URL.

## API
- `GET /health` — service status
- `GET /signals` — all recorded trades
- `GET /summary` — virtual balance and performance
- `POST /signal` — record a simulated trade
- `POST /mark` — submit a mark price and test SL/TP

## Important limitations
This is a local prototype, not a hosted website or webhook. It does not fetch live prices, receive TradingView alerts automatically, connect to CoinDCX, or place live orders. Mark prices must be supplied manually. Fees, slippage, funding and price gaps are not modeled. The app has no login or access control; do not deploy it publicly until authentication and security protections are added. The paper-trade sizing currently uses a fixed $10 risk budget for every new trade and does not reserve aggregate risk across multiple open trades.
