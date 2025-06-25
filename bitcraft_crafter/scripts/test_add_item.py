from db_helpers import add_inventory_item

# Test adding a sample item
add_inventory_item(
    item_name="Rough Wood Trunk",
    tier="I",
    category="Cargo",
    is_craftable=False,
    source="Dead Tree",
    notes="Base material for planks"
)
