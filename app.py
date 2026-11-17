#!/usr/bin/env python3
"""Paper-trading journal. No exchange connection and no real order execution."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

DB_PATH = os.environ.get("PAPER_DB", "paper_trades.sqlite3")
STARTING_BALANCE = 1000.0
RISK_FRACTION = 0.01


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            closed_at TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit REAL NOT NULL,
            quantity REAL NOT NULL,
            risk_amount REAL NOT NULL,
            status TEXT NOT NULL,
            exit_price REAL,
            pnl REAL
        )
    """)
    db.commit()
    return db


def json_response(handler, status, payload):
    body = json.dumps(payload, indent=2).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        # Keep the local prototype's console output quiet.
        pass

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 100_000:
            raise ValueError("Send a JSON body smaller than 100 KB.")
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object.")
        return data

    def do_GET(self):
        path = urlparse(self.path).path
        db = connect()
        try:
            if path == "/health":
                return json_response(self, 200, {"status": "ok", "mode": "PAPER_ONLY"})
            if path == "/signals":
                rows = db.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
                return json_response(self, 200, {"trades": [dict(r) for r in rows]})
            if path == "/summary":
                rows = db.execute("SELECT status, pnl, risk_amount FROM trades").fetchall()
                closed = [r for r in rows if r["status"] == "CLOSED"]
                pnl = sum((r["pnl"] or 0) for r in closed)
                wins = sum(1 for r in closed if (r["pnl"] or 0) > 0)
                return json_response(self, 200, {
                    "mode": "PAPER_ONLY",
                    "starting_balance": STARTING_BALANCE,
                    "virtual_balance": round(STARTING_BALANCE + pnl, 2),
                    "open_trades": sum(1 for r in rows if r["status"] == "OPEN"),
                    "closed_trades": len(closed),
                    "wins": wins,
                    "losses": len(closed) - wins,
                    "realized_pnl": round(pnl, 2)
                })
            return json_response(self, 404, {"error": "Route not found"})
        finally:
            db.close()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.read_json()
            if path == "/signal":
                return self.create_signal(data)
            if path == "/mark":
                return self.mark_price(data)
            return json_response(self, 404, {"error": "Route not found"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return json_response(self, 400, {"error": str(exc)})
        except Exception as exc:
            return json_response(self, 500, {"error": "Internal error", "detail": str(exc)})

    def create_signal(self, data):
        symbol = str(data.get("symbol", "")).strip().upper()
        side = str(data.get("side", "")).strip().upper()
        if not symbol or len(symbol) > 30:
            raise ValueError("symbol is required (maximum 30 characters).")
        if side not in ("LONG", "SHORT"):
            raise ValueError("side must be LONG or SHORT.")

        entry = float(data["entry"])
        stop = float(data["stop_loss"])
        target = float(data["take_profit"])
        if min(entry, stop, target) <= 0:
            raise ValueError("Prices must be greater than zero.")
        if side == "LONG" and not (stop < entry < target):
            raise ValueError("For LONG: stop_loss < entry < take_profit.")
        if side == "SHORT" and not (target < entry < stop):
            raise ValueError("For SHORT: take_profit < entry < stop_loss.")

        distance = abs(entry - stop)
        risk = STARTING_BALANCE * RISK_FRACTION
        quantity = risk / distance

        db = connect()
        try:
            cur = db.execute("""
                INSERT INTO trades
                (created_at, symbol, side, entry, stop_loss, take_profit,
                 quantity, risk_amount, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
            """, (now(), symbol, side, entry, stop, target, quantity, risk))
            db.commit()
            return json_response(self, 201, {
                "message": "Simulated trade recorded. No real order was placed.",
                "trade_id": cur.lastrowid,
                "symbol": symbol, "side": side,
                "entry": entry, "stop_loss": stop, "take_profit": target,
                "quantity": round(quantity, 8),
                "risk_budget": round(risk, 2),
                "status": "OPEN", "mode": "PAPER_ONLY"
            })
        finally:
            db.close()

    def mark_price(self, data):
        symbol = str(data.get("symbol", "")).strip().upper()
        price = float(data["price"])
        if not symbol or price <= 0:
            raise ValueError("A symbol and positive price are required.")

        db = connect()
        try:
            rows = db.execute(
                "SELECT * FROM trades WHERE symbol=? AND status='OPEN'", (symbol,)
            ).fetchall()
            closed = []
            for trade in rows:
                side = trade["side"]
                reason = None
                if side == "LONG":
                    if price <= trade["stop_loss"]:
                        reason = "STOP_LOSS"
                    elif price >= trade["take_profit"]:
                        reason = "TAKE_PROFIT"
                    move = price - trade["entry"]
                else:
                    if price >= trade["stop_loss"]:
                        reason = "STOP_LOSS"
                    elif price <= trade["take_profit"]:
                        reason = "TAKE_PROFIT"
                    move = trade["entry"] - price

                if reason:
                    pnl = move * trade["quantity"]
                    db.execute("""
                        UPDATE trades SET status='CLOSED', closed_at=?,
                        exit_price=?, pnl=? WHERE id=?
                    """, (now(), price, pnl, trade["id"]))
                    closed.append({
                        "trade_id": trade["id"], "exit_reason": reason,
                        "exit_price": price, "pnl": round(pnl, 2)
                    })
            db.commit()
            return json_response(self, 200, {
                "symbol": symbol, "mark_price": price,
                "closed_trades": closed,
                "note": "Simplified paper fills; fees, slippage and gaps are not modeled."
            })
        finally:
            db.close()


if __name__ == "__main__":
    connect().close()
    print("Paper-trading server: http://127.0.0.1:8000 (no live trading)")
    HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
