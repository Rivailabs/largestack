import pytest
from inventory import add_item, adjust_stock, low_stock, inventory_value, clear_inventory

@pytest.fixture(autouse=True)
def reset_inventory():
    clear_inventory()
    yield

class TestInventory:
    def test_add_item_and_low_stock(self):
        add_item('sku1', 'Keyboard', 5, 100, reorder_level=6)
        low = low_stock()
        assert len(low) == 1
        assert low[0]['sku'] == 'sku1'

    def test_adjust_stock_and_value(self):
        add_item('sku1', 'Keyboard', 5, 100, reorder_level=6)
        adjust_stock('sku1', 3)
        assert inventory_value() == 800

    def test_negative_stock_raises(self):
        add_item('sku1', 'Keyboard', 5, 100)
        with pytest.raises(ValueError, match="Stock cannot become negative"):
            adjust_stock('sku1', -10)

    def test_add_negative_quantity_raises(self):
        with pytest.raises(ValueError, match="Quantity cannot be negative"):
            add_item('sku2', 'Mouse', -1, 50)

    def test_add_negative_price_raises(self):
        with pytest.raises(ValueError, match="Price cannot be negative"):
            add_item('sku2', 'Mouse', 1, -50)

    def test_adjust_nonexistent_sku_raises(self):
        with pytest.raises(KeyError):
            adjust_stock('nonexistent', 1)
