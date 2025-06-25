from collections import defaultdict
import math
import sqlite3
import os

# Get path to database
def get_db_connection():
    """
    Keep this function for backwards compatibility with standalone scripts
    But API routes will use the Flask g object version
    """
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "bitcraft.db"))
    return sqlite3.connect(db_path)

def add_inventory_item(item_name, tier, category, is_craftable, source="", notes=""):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Prepare item data
    item_data = {
        "ItemName": item_name.strip(),
        "Tier": tier.strip(),
        "Category": category.strip(),
        "IsCraftable": is_craftable,
        "Source": source.strip(),
        "Notes": notes.strip()
    }

    try:
        cursor.execute('''
            INSERT INTO Inventory (ItemName, Tier, Quantity, Category, Source, IsCraftable, Notes)
            VALUES (:ItemName, :Tier, 0, :Category, :Source, :IsCraftable, :Notes)
        ''', item_data)
        conn.commit()
        print(f"Item added: {item_name} (Tier {tier})")
    except sqlite3.IntegrityError:
        print(f"Item already exists: {item_name} (Tier {tier})")
    finally:
        conn.close()

def add_recipe(recipe_name, output_item, output_qty, is_shaped=False, notes=""):
    conn = get_db_connection()
    cursor = conn.cursor()

    recipe_data = {
        "RecipeName": recipe_name.strip(),
        "OutputItem": output_item.strip(),
        "OutputQty": output_qty,
        "IsShaped": is_shaped,
        "Notes": notes.strip()
    }

    try:
        cursor.execute('''
            INSERT INTO Recipes (RecipeName, OutputItem, OutputQty, IsShaped, Notes)
            VALUES (:RecipeName, :OutputItem, :OutputQty, :IsShaped, :Notes)
        ''', recipe_data)
        conn.commit()
        recipe_id = cursor.lastrowid
        print(f"Recipe added: {recipe_name} (ID: {recipe_id})")
        return recipe_id
    except sqlite3.IntegrityError:
        print(f"Recipe already exists: {recipe_name}")
        return None
    finally:
        conn.close()

def add_ingredients(recipe_id, ingredients):
    """
    ingredients = list of dicts, e.g.:
    [
        {"InputItem": "Rough Wood Trunk", "Quantity": 1},
        {"InputItem": "Glue", "Quantity": 1}
    ]
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    for ing in ingredients:
        ing_data = {
            "RecipeID": recipe_id,
            "InputItem": ing["InputItem"].strip(),
            "Quantity": ing["Quantity"]
        }

        cursor.execute('''
            INSERT INTO Ingredients (RecipeID, InputItem, Quantity)
            VALUES (:RecipeID, :InputItem, :Quantity)
        ''', ing_data)

    conn.commit()
    conn.close()
    print(f"Ingredients added for Recipe ID {recipe_id}")

def get_required_materials(item_name, quantity=1, conn=None):
    internal = False
    if conn is None:
        conn = get_db_connection()
        internal = True

    cursor = conn.cursor()

    # Get recipe that outputs this item
    cursor.execute('''
        SELECT RecipeID, OutputQty FROM Recipes WHERE OutputItem = ?
    ''', (item_name,))
    recipe_row = cursor.fetchone()

    if not recipe_row:
        # No recipe = base item
        return {item_name: quantity}

    recipe_id, output_qty = recipe_row
    multiplier = math.ceil(quantity / output_qty)

    # Get ingredients
    cursor.execute('''
        SELECT InputItem, Quantity FROM Ingredients WHERE RecipeID = ?
    ''', (recipe_id,))
    ingredients = cursor.fetchall()

    # Recursive call
    total_materials = defaultdict(int)

    for input_item, input_qty in ingredients:
        required_qty = input_qty * multiplier
        sub_materials = get_required_materials(input_item, required_qty, conn)
        for name, qty in sub_materials.items():
            total_materials[name] += qty

    if internal:
        conn.close()

    return dict(total_materials)

def get_full_tree(item_name, quantity=1, conn=None, visited=None):
    """
    Enhanced tree building with cycle detection and better error handling
    """
    if visited is None:
        visited = set()
    
    # Cycle detection
    if item_name in visited:
        return {
            "quantity": quantity,
            "produced_by": None,
            "ingredients": {},
            "error": f"Circular dependency detected for {item_name}"
        }
    
    visited.add(item_name)
    
    internal = False
    if conn is None:
        conn = get_db_connection()
        internal = True

    cursor = conn.cursor()

    try:
        # Look up the recipe
        cursor.execute('SELECT RecipeID, OutputQty FROM Recipes WHERE OutputItem = ?', (item_name,))
        recipe_row = cursor.fetchone()

        if not recipe_row:
            # Base material
            node = {
                "quantity": quantity,
                "produced_by": None,
                "ingredients": {},
                "is_base_material": True
            }
            visited.remove(item_name)
            if internal:
                conn.close()
            return node

        recipe_id, output_qty = recipe_row
        
        # Calculate how many times we need to run the recipe
        multiplier = math.ceil(quantity / output_qty)
        actual_output = multiplier * output_qty

        # Get all ingredients for the recipe
        cursor.execute('SELECT InputItem, Quantity FROM Ingredients WHERE RecipeID = ?', (recipe_id,))
        ingredients = cursor.fetchall()

        # Recursively build subtrees
        tree = {
            "quantity": quantity,
            "actual_output": actual_output,
            "recipe_runs": multiplier,
            "produced_by": item_name,
            "ingredients": {},
            "is_base_material": False
        }

        for input_item, qty in ingredients:
            total_qty = qty * multiplier
            tree["ingredients"][input_item] = get_full_tree(
                input_item, total_qty, conn, visited.copy()
            )

        visited.remove(item_name)
        if internal:
            conn.close()

        return tree
        
    except Exception as e:
        visited.remove(item_name)
        if internal:
            conn.close()
        return {
            "quantity": quantity,
            "produced_by": None,
            "ingredients": {},
            "error": f"Error processing {item_name}: {str(e)}"
        }

# REPLACE flatten_tree_to_shopping_list with this enhanced version:
def flatten_tree_to_shopping_list(tree, item_name="root"):
    """
    Enhanced shopping list with error reporting
    """
    shopping_list = defaultdict(int)
    errors = []

    def walk(node, current_item):
        if "error" in node:
            errors.append(f"{current_item}: {node['error']}")
            return
            
        if not node.get("ingredients") or node.get("is_base_material", False):
            shopping_list[current_item] += node["quantity"]
        else:
            for child_item, child_node in node["ingredients"].items():
                walk(child_node, child_item)

    walk(tree, item_name)
    
    # For backwards compatibility, return just the shopping list if no errors
    if not errors:
        return dict(shopping_list)
    
    return {
        "shopping_list": dict(shopping_list),
        "errors": errors
    }