import os, time, uuid
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

from src.pricing import quote_vpc_amount
from src.address_pool import AddressPool
from src.order_store import OrderStore
from src.providers.router import quote_crypto_amount
from src.providers.check_payment_stub import check_payment_stub
from src.providers.check_payment_btc import check_payment_btc
from src.solana_sender import send_vpc_tokens

load_dotenv()

PORT = int(os.getenv("PORT", "8080"))
ORDER_TTL_MINUTES = int(os.getenv("ORDER_TTL_MINUTES", "30"))
MIN_PURCHASE_USD = float(os.getenv("MIN_PURCHASE_USD", "20"))

app = Flask(__name__, template_folder="templates")
store = OrderStore(path="data/orders.json")
pool = AddressPool(ttl_minutes=ORDER_TTL_MINUTES)

@app.get("/")
def home():
    return render_template("index.html")

@app.post("/api/order")
def create_order():
    body = request.get_json(force=True, silent=True) or {}
    usd = float(body.get("usd") or 0)
    method = (body.get("method") or "").strip()
    buyer = (body.get("buyer_solana") or "").strip()
    promo = (body.get("promo") or "").strip()

    if usd < MIN_PURCHASE_USD:
        return jsonify(error=f"Minimum purchase is ${MIN_PURCHASE_USD:.0f}"), 400
    if not buyer or len(buyer) < 20:
        return jsonify(error="Please enter a valid Solana address to receive VPC."), 400

    pool_key = method
    if method == "usdt_sol":
        pool_key = "sol"
    if method == "usdt_erc20":
        pool_key = "eth"
    if method == "usdt_trc20":
        pool_key = "trx"

    deposit = pool.checkout(pool_key)
    if not deposit:
        return jsonify(error=f"No available deposit addresses for {method.upper()}. Add more in .env."), 400

    vpc_amount = quote_vpc_amount(usd, promo)
    pay_amount, pay_symbol = quote_crypto_amount(usd, method)

    order_id = uuid.uuid4().hex[:12]
    created = int(time.time())
    expires = created + ORDER_TTL_MINUTES * 60

    order = {
        "order_id": order_id,
        "status": "PENDING",
        "created_at": created,
        "expires_at": expires,
        "usd": round(usd, 2),
        "method": method,
        "pool_key": pool_key,
        "deposit_address": deposit["address"],
        "deposit_slot": deposit["slot"],
        "buyer_solana": buyer,
        "vpc_amount": vpc_amount,
        "pay_amount": pay_amount,
        "pay_symbol": pay_symbol,
        "promo": promo,
        "txid": None,
        "notes": "",
    }

    store.put(order)

    return jsonify(
        order_id=order_id,
        status=order["status"],
        deposit_address=order["deposit_address"],
        pay_amount=order["pay_amount"],
        pay_symbol=order["pay_symbol"],
        vpc_amount=order["vpc_amount"],
        expires_in=f"{ORDER_TTL_MINUTES} minutes",
    )

@app.get("/api/order/<order_id>")
def get_order(order_id: str):
    o = store.get(order_id)
    if not o:
        return jsonify(error="Not found"), 404

    now = int(time.time())
    if o["status"] == "PENDING" and now > o["expires_at"]:
        o["status"] = "EXPIRED"
        store.put(o)
        pool.release(o["pool_key"], o["deposit_slot"])

    return jsonify(
        order_id=o["order_id"],
        status=o["status"],
        deposit_address=o["deposit_address"],
        usd=o["usd"],
        method=o["method"],
        vpc_amount=o["vpc_amount"],
        pay_amount=o["pay_amount"],
        pay_symbol=o["pay_symbol"],
        txid=o.get("txid"),
    )

def background_loop():
    while True:
        time.sleep(10)
        now = int(time.time())
        orders = store.all()
        changed = False

        for o in orders:
            if o["status"] != "PENDING":
                continue

            if now > o["expires_at"] and o["method"] != "bitcoin":
                o["status"] = "EXPIRED"
                pool.release(o["pool_key"], o["deposit_slot"])
                changed = True
                continue

            if o["method"] == "bitcoin":
                paid, txid = check_payment_btc(o)
            else:
                paid, txid = check_payment_stub(o)

            if paid:
                o["status"] = "PAID"
                o["txid"] = txid

                try:
                    tx_sig = send_vpc_tokens(o["buyer_solana"], o["vpc_amount"])
                    o["notes"] = f"VPC sent in TX: {tx_sig}"
                except Exception as e:
                    o["notes"] = f"Failed to send VPC: {str(e)}"

                pool.release(o["pool_key"], o["deposit_slot"])
                changed = True

        if changed:
            store.save()

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    import threading
    t = threading.Thread(target=background_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
