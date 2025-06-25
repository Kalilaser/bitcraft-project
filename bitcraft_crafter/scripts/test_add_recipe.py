from db_helpers import get_full_tree, flatten_tree_to_shopping_list

# Set target project item
item = "Wooden Chair"
qty = 2

tree = get_full_tree(item, qty)
shopping_list = flatten_tree_to_shopping_list(tree)

print(f"🪵 Full crafting tree for {qty}x {item}:")
print(tree)

print("\n🛒 Shopping list:")
for name, count in shopping_list.items():
    print(f"  - {name}: {count}")