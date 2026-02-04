def quote_vpc_amount(usd, promo):
    VPC_PRICE_USD = 0.0019
    discount = 0.10 if promo.lower() == "viewplay10" else 0
    effective_price = VPC_PRICE_USD * (1 - discount)
    return int(usd / effective_price)