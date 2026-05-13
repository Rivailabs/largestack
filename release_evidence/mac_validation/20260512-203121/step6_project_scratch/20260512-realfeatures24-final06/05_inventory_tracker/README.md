# Inventory Tracker

A simple Python inventory tracker with functions to add items, adjust stock, check low stock, and compute total inventory value.

## Usage

```python
from inventory import add_item, adjust_stock, low_stock, inventory_value

add_item('sku1', 'Keyboard', 5, 100, reorder_level=6)
print(low_stock())  # [{'sku': 'sku1', ...}]

adjust_stock('sku1', 3)
print(inventory_value())  # 800
```

## Running Tests

Install pytest:
```
pip install pytest
```

Run tests:
```
pytest tests/
```

## Largestack Smoke Test

Install largestack:
```
pip install largestack
```

Run the smoke test:
```
python -c "import asyncio; from largestack_app import run_largestack_smoke; print(asyncio.run(run_largestack_smoke()))"
```
