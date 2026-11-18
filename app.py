#!/usr/bin/env python3
"""INR-denominated paper-trading journal. No exchange connection or real orders."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64, hmac, json, os, sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

DB_PATH = os.environ.get("PAPER_DB", "paper_trades.sqlite3")

def now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
        closed_at TEXT, symbol TEXT NOT NULL, side TEXT NOT NULL,
        entry REAL NOT NULL, stop_loss REAL NOT NULL, take_profit REAL NOT NULL,
        quantity REAL NOT NULL, risk_amount REAL NOT NULL, status TEXT NOT NULL,
        exit_price REAL, pnl REAL)""")
    # Safe, additive migration for journals created by earlier versions.
    columns = {r["name"] for r in db.execute("PRAGMA table_info(trades)")}
    for name, declaration in (
        ("remaining_quantity", "REAL NOT NULL DEFAULT 0"),
        ("realized_pnl", "REAL NOT NULL DEFAULT 0"),
        ("partial_exits", "TEXT NOT NULL DEFAULT '[]'")
    ):
        if name not in columns:
            db.execute(f"ALTER TABLE trades ADD COLUMN {name} {declaration}")
    db.execute("UPDATE trades SET remaining_quantity=quantity WHERE remaining_quantity=0 AND status='OPEN'")
    db.commit()
    return db

def json_response(handler, status, payload):
    body = json.dumps(payload, indent=2).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args): pass

    def authorized(self):
        username, password = os.environ.get("APP_USERNAME", ""), os.environ.get("APP_PASSWORD", "")
        header = self.headers.get("Authorization", "")
        if not username or not password or not header.startswith("Basic "): return False
        try:
            user, supplied = base64.b64decode(header[6:], validate=True).decode().split(":", 1)
        except (ValueError, UnicodeDecodeError): return False
        return hmac.compare_digest(user, username) and hmac.compare_digest(supplied, password)

    def require_auth(self):
        if self.authorized(): return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Paper Trading Journal", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 100_000: raise ValueError("Send a JSON body smaller than 100 KB.")
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict): raise ValueError("JSON body must be an object.")
        return data

    def do_GET(self):
        if not self.require_auth(): return
        path = urlparse(self.path).path
        if path in ("/", "/dashboard.html"):
            try:
                with open(os.path.join(os.path.dirname(__file__), "dashboard.html"), "rb") as f: body = f.read()
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            except FileNotFoundError: json_response(self, 404, {"error": "dashboard.html is missing"})
            return
        db = connect()
        try:
            if path == "/health": return json_response(self, 200, {"status":"ok","mode":"PAPER_ONLY"})
            if path == "/signals":
                rows = db.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
                return json_response(self, 200, {"trades":[dict(r) for r in rows]})
            if path == "/summary":
                rows = db.execute("SELECT status,pnl FROM trades").fetchall()
                closed = [r for r in rows if r["status"] == "CLOSED"]
                pnl = sum((r["pnl"] or 0) for r in closed)
                wins = sum(1 for r in closed if (r["pnl"] or 0) > 0)
                return json_response(self, 200, {
                    "mode":"PAPER_ONLY", "realized_pnl":round(pnl,2),
                    "open_trades":sum(1 for r in rows if r["status"]=="OPEN"),
                    "closed_trades":len(closed), "wins":wins, "losses":len(closed)-wins
                })
            return json_response(self, 404, {"error":"Route not found"})
        finally: db.close()

    def do_POST(self):
        if not self.require_auth(): return
        path = urlparse(self.path).path
        try:
            data = self.read_json()
            if path == "/signal": return self.create_signal(data)
            if path == "/mark": return self.mark_price(data)
            return json_response(self,404,{"error":"Route not found"})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            return json_response(self,400,{"error":str(exc)})
        except Exception as exc:
            return json_response(self,500,{"error":"Internal error","detail":str(exc)})

    def create_signal(self, data):
        symbol = str(data.get("symbol","")).strip().upper()
        side = str(data.get("side","")).strip().upper()
        if not symbol or len(symbol)>30: raise ValueError("Enter a symbol (maximum 30 characters).")
        if side not in ("LONG","SHORT"): raise ValueError("Direction must be LONG or SHORT.")
        entry, stop, target, quantity = (float(data[k]) for k in ("entry","stop_loss","take_profit","quantity"))
        if min(entry,stop,target,quantity)<=0: raise ValueError("Prices and quantity must be greater than zero.")
        if side=="LONG" and not stop<entry<target: raise ValueError("For LONG: stop-loss < entry < take-profit.")
        if side=="SHORT" and not target<entry<stop: raise ValueError("For SHORT: take-profit < entry < stop-loss.")
        risk = abs(entry-stop)*quantity
        db=connect()
        try:
            cur=db.execute("""INSERT INTO trades
                (created_at,symbol,side,entry,stop_loss,take_profit,quantity,risk_amount,status,remaining_quantity)
                VALUES (?,?,?,?,?,?,?,?,'OPEN',?)""",
                (now(),symbol,side,entry,stop,target,quantity,risk,quantity))
            db.commit()
            return json_response(self,201,{"message":"Paper trade saved. No real order was placed.",
                "trade_id":cur.lastrowid,"symbol":symbol,"side":side,"entry":entry,
                "stop_loss":stop,"take_profit":target,"quantity":quantity,
                "risk_amount":round(risk,2),"remaining_quantity":quantity,
                "partial_plan":[25,50,75,100],"status":"OPEN","mode":"PAPER_ONLY"})
        finally: db.close()

    def mark_price(self, data):
        symbol=str(data.get("symbol","")).strip().upper()
        price=float(data["price"])
        if not symbol or price<=0: raise ValueError("Enter a symbol and positive test price.")
        db=connect()
        try:
            rows=db.execute("SELECT * FROM trades WHERE symbol=? AND status='OPEN'",(symbol,)).fetchall()
            updates=[]
            for trade in rows:
                side=trade["side"]
                stop_hit = price<=trade["stop_loss"] if side=="LONG" else price>=trade["stop_loss"]
                exits=json.loads(trade["partial_exits"] or "[]")
                remaining=float(trade["remaining_quantity"])
                realized=float(trade["realized_pnl"] or 0)
                if stop_hit:
                    exit_price=trade["stop_loss"]
                    pnl=(exit_price-trade["entry"])*remaining*(1 if side=="LONG" else -1)
                    realized+=pnl
                    exits.append({"stage":"STOP LOSS","price":exit_price,"quantity":remaining,"pnl":round(pnl,2)})
                    db.execute("""UPDATE trades SET status='CLOSED',closed_at=?,exit_price=?,pnl=?,
                        remaining_quantity=0,realized_pnl=?,partial_exits=? WHERE id=?""",
                        (now(),exit_price,realized,realized,json.dumps(exits),trade["id"]))
                    updates.append({"trade_id":trade["id"],"event":"STOP LOSS","pnl":round(pnl,2),"total_pnl":round(realized,2)})
                    continue
                distance=trade["take_profit"]-trade["entry"] if side=="LONG" else trade["entry"]-trade["take_profit"]
                progress=(price-trade["entry"])/(trade["take_profit"]-trade["entry"]) if side=="LONG" else (trade["entry"]-price)/(trade["entry"]-trade["take_profit"])
                stages=[25,50,75,100]
                for stage in stages:
                    if stage in [e.get("stage_percent") for e in exits]: continue
                    if progress+1e-12 < stage/100: continue
                    exit_price=trade["entry"]+(trade["take_profit"]-trade["entry"])*(stage/100)
                    tranche=remaining if stage==100 else min(remaining,trade["quantity"]*0.25)
                    pnl=(exit_price-trade["entry"])*tranche*(1 if side=="LONG" else -1)
                    realized+=pnl; remaining=max(0,remaining-tranche)
                    exits.append({"stage_percent":stage,"stage":f"TARGET {stage}%","price":exit_price,"quantity":tranche,"pnl":round(pnl,2)})
                    updates.append({"trade_id":trade["id"],"event":f"TARGET {stage}%","exit_price":round(exit_price,8),"quantity_closed":round(tranche,8),"pnl":round(pnl,2),"remaining_quantity":round(remaining,8)})
                if remaining<=1e-12:
                    db.execute("""UPDATE trades SET status='CLOSED',closed_at=?,exit_price=?,pnl=?,
                        remaining_quantity=0,realized_pnl=?,partial_exits=? WHERE id=?""",
                        (now(),trade["take_profit"],realized,realized,json.dumps(exits),trade["id"]))
                else:
                    db.execute("UPDATE trades SET remaining_quantity=?,realized_pnl=?,partial_exits=? WHERE id=?",
                        (remaining,realized,json.dumps(exits),trade["id"]))
            db.commit()
            return json_response(self,200,{"symbol":symbol,"mark_price":price,"events":updates,
                "note":"Simplified paper fills at planned target levels or stop-loss. Fees, funding, slippage and gaps are not modeled."})
        finally: db.close()

if __name__=="__main__":
    connect().close()
    if not os.environ.get("APP_USERNAME") or not os.environ.get("APP_PASSWORD"):
        raise SystemExit("Set APP_USERNAME and APP_PASSWORD before starting the server.")
    host="0.0.0.0"; port=int(os.environ.get("PORT","8000"))
    print(f"INR paper-trading server listening on {host}:{port} (paper mode only)")
    ThreadingHTTPServer((host,port),Handler).serve_forever()
