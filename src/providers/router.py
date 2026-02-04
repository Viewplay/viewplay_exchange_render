import requests

COINGECKO_IDS = {
    "usdt_sol": "tether",
    "usdt_erc20": "tether",
    "usdt_trc20": "tether",
    "bitcoin": "bitcoin",
}

def quote_crypto_amount(usd, method):
    coingecko_id = COINGECKO_IDS.get(method, "tether")
    try:
        res = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coingecko_id}&vs_currencies=usd")
        res.raise_for_status()
        price = res.json()[coingecko_id]["usd"]
    except Exception:
        price = 1.0  # fallback

    crypto_amount = round(usd / price, 8)
    return crypto_amount, method.upper()
