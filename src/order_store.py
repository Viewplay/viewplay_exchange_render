import json
import os

class OrderStore:
    def __init__(self, path):
        self.path = path
        self.orders = []
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                self.orders = json.load(f)

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.orders, f)

    def put(self, order):
        self.orders = [o for o in self.orders if o["order_id"] != order["order_id"]]
        self.orders.append(order)
        self.save()

    def get(self, order_id):
        for o in self.orders:
            if o["order_id"] == order_id:
                return o
        return None

    def all(self):
        return self.orders