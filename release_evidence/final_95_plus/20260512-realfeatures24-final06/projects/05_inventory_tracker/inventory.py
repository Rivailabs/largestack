import json
import os

_inventory = {}


def add_item(sku, name, quantity, price, reorder_level=0):
    if quantity < 0:
        raise ValueError("Quantity cannot be negative")
    if price < 0:
        raise ValueError("Price cannot be negative")
    _inventory[sku] = {
        'sku': sku,
        'name': name,
        'quantity': quantity,
        'price': price,
        'reorder_level': reorder_level
    }


def adjust_stock(sku, amount):
    if sku not in _inventory:
        raise KeyError(f"SKU {sku} not found")
    new_quantity = _inventory[sku]['quantity'] + amount
    if new_quantity < 0:
        raise ValueError("Stock cannot become negative")
    _inventory[sku]['quantity'] = new_quantity


def low_stock():
    return [item for item in _inventory.values() if item['quantity'] <= item['reorder_level']]


def inventory_value():
    return sum(item['quantity'] * item['price'] for item in _inventory.values())


def clear_inventory():
    _inventory.clear()
