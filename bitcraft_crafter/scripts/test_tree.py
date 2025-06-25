from db_helpers import get_required_materials

result = get_required_materials("Wooden Plank", 8)
print("Materials needed to craft 8 Wooden Planks:")
for item, qty in result.items():
    print(f"  - {item}: {qty}")