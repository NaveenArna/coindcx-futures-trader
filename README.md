# CoinDCX Futures Trader — Paper Trading

A beginner-friendly **paper-trading-only** starter. It records simulated LONG/SHORT trades and tests stop-loss/take-profit outcomes. It does not connect to CoinDCX, TradingView, or any broker and cannot place real orders.

## Mobile dashboard
The app includes a responsive dashboard in `dashboard.html`. When the server is running, open its root URL in Safari. You can:
- Record simulated LONG or SHORT trades with entry, stop-loss and take-profit.
- Review open and closed trades, virtual balance and realized P&L.
- Enter a test/mark price to check whether open trades reach SL or TP.

## Deploy on Render
The repository includes `render.yaml` for a Render Blueprint deployment.
1. Sign in to Render and choose **New → Blueprint**.
2. Connect GitHub and select `NaveenArna/coindcx-futures-trader`, branch `main`.
3. Review the service named `coindcx-paper-journal`.
4. When prompted, set `APP_USERNAME` to a username and `APP_PASSWORD` to a long, unique password. Do not put secrets in GitHub.
5. Choose the Free plan only for a temporary test, then create/deploy the Blueprint.
6. Open the generated `onrender.com` URL in Safari and sign in using the credentials you set.

The server requires both environment variables and protects the dashboard and API with HTTP Basic Authentication.

## Important free-hosting limitation
Render Free web services sleep after 15 minutes without traffic and their local filesystem is ephemeral. This prototype stores its SQLite journal in a local file, so paper-trade history can be lost when the free service sleeps, restarts or redeploys. Do not use this free setup as a permanent trading journal. Persistent disk storage requires a paid Render web service; alternatively, we can later move the journal to a suitable external database. Render's free service can also take about a minute to wake after inactivity.

## Safety defaults and limitations
- Virtual starting balance: $1,000
- Fixed risk budget: $10 per trade (1% of the starting balance)
- No exchange credentials or API keys; no live order execution.
- No live market prices or automatic TradingView alerts; mark prices must be entered manually.
- Fees, slippage, funding and price gaps are not modeled.
- The app has no multi-user account system; the single deployment password protects the whole journal.
- Position sizing uses a fixed $10 risk budget for every new trade and does not reserve aggregate risk across multiple open trades.

## Run locally
Python 3.10+ (standard library only). Set `APP_USERNAME` and `APP_PASSWORD`, then run:
```bash
python app.py
```
The local server listens on port 8000 by default, or the port in the `PORT` environment variable.

## API
- `GET /health` — service status
- `GET /signals` — all recorded trades
- `GET /summary` — virtual balance and performance
- `POST /signal` — record a simulated trade
- `POST /mark` — submit a mark price and test SL/TP
