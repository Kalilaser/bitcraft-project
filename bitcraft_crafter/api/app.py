from flask import Flask, request, jsonify, g
from flask_cors import CORS
from functools import wraps
import sys
import os
import sqlite3
import traceback

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import db_helpers

app = Flask(__name__)
CORS(app)

# NEW: Flask database connection management
def get_db():
    if 'db' not in g:
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "bitcraft.db"))
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row  # This allows dict-like access to rows
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.teardown_appcontext
def close_db(error):
    close_db()

# NEW: Input validation decorator
def validate_json(*required_fields):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return jsonify({"error": "Content-Type must be application/json"}), 400
            
            data = request.get_json()
            if not data:
                return jsonify({"error": "No JSON data provided"}), 400
            
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400
            
            return f(*args, **kwargs)
        return wrapper
    return decorator

# NEW: Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

# UPDATED: Use Flask's get_db() instead of db_helpers.get_db_connection()
@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT ItemName, Tier, Quantity, Category, Source, IsCraftable, Notes FROM Inventory')
        rows = cursor.fetchall()

        # Convert each row to a dictionary
        inventory = [dict(row) for row in rows]
        return jsonify(inventory)
    except Exception as e:
        print(f"Error fetching inventory: {traceback.format_exc()}")
        return jsonify({"error": "Failed to fetch inventory"}), 500

@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    try:
        db = get_db()
        cursor = db.cursor()
        # Get all recipes
        cursor.execute('SELECT RecipeID, RecipeName, OutputItem, OutputQty, IsShaped, Notes FROM Recipes')
        recipes = []
        for row in cursor.fetchall():
            recipe_id = row['RecipeID']
            # Get ingredients for this recipe
            cursor.execute('SELECT InputItem, Quantity FROM Ingredients WHERE RecipeID = ?', (recipe_id,))
            ingredients = [{"InputItem": ing['InputItem'], "Quantity": ing['Quantity']} for ing in cursor.fetchall()]
            recipes.append({
                "RecipeID": row['RecipeID'],
                "RecipeName": row['RecipeName'],
                "OutputItem": row['OutputItem'],
                "OutputQty": row['OutputQty'],
                "IsShaped": bool(row['IsShaped']),
                "Notes": row['Notes'],
                "Ingredients": ingredients
            })
        return jsonify(recipes)
    except Exception as e:
        print(f"Error fetching recipes: {traceback.format_exc()}")
        return jsonify({"error": "Failed to fetch recipes"}), 500

@app.route('/api/inventory/<item_name>/<tier>', methods=['PATCH'])
def update_inventory(item_name, tier):
    try:
        data = request.get_json()
        if not data or 'Quantity' not in data:
            return jsonify({"error": "Quantity is required"}), 400
        
        new_quantity = data.get("Quantity")
        if not isinstance(new_quantity, int) or new_quantity < 0:
            return jsonify({"error": "Quantity must be a non-negative integer"}), 400
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            UPDATE Inventory SET Quantity = ? WHERE ItemName = ? AND Tier = ?
        ''', (new_quantity, item_name, tier))
        
        if cursor.rowcount == 0:
            return jsonify({"error": "Item not found"}), 404
        
        db.commit()
        return jsonify({"success": True, "item": item_name, "tier": tier, "new_quantity": new_quantity})
    except Exception as e:
        print(f"Error updating inventory: {traceback.format_exc()}")
        return jsonify({"error": "Failed to update inventory"}), 500

# UPDATED: Add validation and better error handling
@app.route('/api/inventory', methods=['POST'])
@validate_json('ItemName', 'Tier', 'Category', 'IsCraftable')
def add_inventory():
    try:
        data = request.get_json()
        
        # Additional validation
        if not isinstance(data['IsCraftable'], bool):
            return jsonify({"error": "IsCraftable must be a boolean"}), 400
        
        if not data['ItemName'].strip():
            return jsonify({"error": "ItemName cannot be empty"}), 400
        
        db_helpers.add_inventory_item(
            data["ItemName"], data["Tier"], data["Category"],
            data["IsCraftable"], data.get("Source", ""), data.get("Notes", "")
        )
        return jsonify({"success": True, "item": data["ItemName"]}), 201
        
    except sqlite3.IntegrityError as e:
        return jsonify({"error": "Item already exists"}), 409
    except Exception as e:
        print(f"Error adding inventory: {traceback.format_exc()}")
        return jsonify({"error": "Internal server error"}), 500

# UPDATED: Add validation
@app.route('/api/recipes', methods=['POST'])
@validate_json('RecipeName', 'OutputItem', 'OutputQty', 'Ingredients')
def add_recipe():
    try:
        data = request.get_json()
        
        # Validate ingredients
        if not isinstance(data['Ingredients'], list) or len(data['Ingredients']) == 0:
            return jsonify({"error": "Ingredients must be a non-empty list"}), 400
        
        for ing in data['Ingredients']:
            if not isinstance(ing, dict) or 'InputItem' not in ing or 'Quantity' not in ing:
                return jsonify({"error": "Each ingredient must have InputItem and Quantity"}), 400
        
        recipe_id = db_helpers.add_recipe(
            data["RecipeName"], data["OutputItem"], data["OutputQty"],
            data.get("IsShaped", False), data.get("Notes", "")
        )
        if recipe_id:
            db_helpers.add_ingredients(recipe_id, data["Ingredients"])
        
        return jsonify({"success": bool(recipe_id), "RecipeID": recipe_id}), 201 if recipe_id else 409
    except Exception as e:
        print(f"Error adding recipe: {traceback.format_exc()}")
        return jsonify({"error": "Failed to add recipe"}), 500

# UPDATED: Add validation and better error handling
@app.route('/api/tree', methods=['POST'])
@validate_json('ItemName')
def get_tree():
    try:
        data = request.get_json()
        item = data["ItemName"]
        qty = data.get("Quantity", 1)
        
        if not isinstance(qty, int) or qty <= 0:
            return jsonify({"error": "Quantity must be a positive integer"}), 400
        
        tree = db_helpers.get_full_tree(item, qty)
        shopping_list = db_helpers.flatten_tree_to_shopping_list(tree, item)
        
        return jsonify({"tree": tree, "shopping_list": shopping_list})
    except Exception as e:
        print(f"Error generating tree: {traceback.format_exc()}")
        return jsonify({"error": "Failed to generate crafting tree"}), 500

@app.route('/api/projects', methods=['GET'])
def get_projects():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT ProjectID, Name, Description, CreatedAt FROM Projects')
        projects = [dict(row) for row in cursor.fetchall()]
        return jsonify(projects)
    except Exception as e:
        print(f"Error fetching projects: {traceback.format_exc()}")
        return jsonify({"error": "Failed to fetch projects"}), 500

# UPDATED: Add validation
@app.route('/api/projects', methods=['POST'])
@validate_json('Name')
def create_project():
    try:
        data = request.get_json()
        name = data["Name"]
        description = data.get("Description", "")
        
        if not name.strip():
            return jsonify({"error": "Project name cannot be empty"}), 400
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('INSERT INTO Projects (Name, Description) VALUES (?, ?)', (name, description))
        project_id = cursor.lastrowid
        
        # Add project items if provided
        items = data.get("Items", [])
        for item in items:
            if 'ItemName' not in item or 'Quantity' not in item:
                return jsonify({"error": "Each item must have ItemName and Quantity"}), 400
            cursor.execute('''
                INSERT INTO ProjectItems (ProjectID, ItemName, Tier, Quantity)
                VALUES (?, ?, ?, ?)
            ''', (project_id, item["ItemName"], item.get("Tier", ""), item["Quantity"]))
        
        db.commit()
        return jsonify({"success": True, "ProjectID": project_id}), 201
    except Exception as e:
        print(f"Error creating project: {traceback.format_exc()}")
        return jsonify({"error": "Failed to create project"}), 500

@app.route('/api/project/<int:project_id>', methods=['GET'])
def get_project(project_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT Name, Description, CreatedAt FROM Projects WHERE ProjectID = ?', (project_id,))
        proj_row = cursor.fetchone()
        if not proj_row:
            return jsonify({"error": "Project not found"}), 404

        cursor.execute('SELECT ItemName, Tier, Quantity FROM ProjectItems WHERE ProjectID = ?', (project_id,))
        items = [{"ItemName": r['ItemName'], "Tier": r['Tier'], "Quantity": r['Quantity']} for r in cursor.fetchall()]

        # Get the tree and shopping list for all project items
        all_trees = []
        all_shopping = {}
        for i in items:
            tree = db_helpers.get_full_tree(i["ItemName"], i["Quantity"])
            all_trees.append({i["ItemName"]: tree})
            slist = db_helpers.flatten_tree_to_shopping_list(tree, i["ItemName"])
            
            # Handle new format that might include errors
            if isinstance(slist, dict) and "shopping_list" in slist:
                slist = slist["shopping_list"]
            
            for k, v in slist.items():
                all_shopping[k] = all_shopping.get(k, 0) + v

        return jsonify({
            "ProjectID": project_id,
            "Name": proj_row['Name'],
            "Description": proj_row['Description'],
            "CreatedAt": proj_row['CreatedAt'],
            "Items": items,
            "AllTrees": all_trees,
            "ShoppingList": all_shopping
        })
    except Exception as e:
        print(f"Error fetching project: {traceback.format_exc()}")
        return jsonify({"error": "Failed to fetch project"}), 500

@app.route('/api/inventory/<item_name>/<tier>', methods=['DELETE'])
def delete_inventory(item_name, tier):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM Inventory WHERE ItemName = ? AND Tier = ?', (item_name, tier))
        
        if cursor.rowcount == 0:
            return jsonify({"error": "Item not found"}), 404
        
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error deleting inventory: {traceback.format_exc()}")
        return jsonify({"error": "Failed to delete item"}), 500

@app.route('/api/recipes/<int:recipe_id>', methods=['DELETE'])
def delete_recipe(recipe_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM Ingredients WHERE RecipeID = ?', (recipe_id,))
        cursor.execute('DELETE FROM Recipes WHERE RecipeID = ?', (recipe_id,))
        
        if cursor.rowcount == 0:
            return jsonify({"error": "Recipe not found"}), 404
        
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error deleting recipe: {traceback.format_exc()}")
        return jsonify({"error": "Failed to delete recipe"}), 500

@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM ProjectItems WHERE ProjectID = ?', (project_id,))
        cursor.execute('DELETE FROM Projects WHERE ProjectID = ?', (project_id,))
        
        if cursor.rowcount == 0:
            return jsonify({"error": "Project not found"}), 404
        
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error deleting project: {traceback.format_exc()}")
        return jsonify({"error": "Failed to delete project"}), 500

@app.route('/api/tree', methods=['GET'])
def get_full_database_tree():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT DISTINCT OutputItem FROM Recipes')
        all_items = [r['OutputItem'] for r in cursor.fetchall()]
        
        all_trees = {}
        for item in all_items:
            all_trees[item] = db_helpers.get_full_tree(item, 1)
        return jsonify(all_trees)
    except Exception as e:
        print(f"Error generating full tree: {traceback.format_exc()}")
        return jsonify({"error": "Failed to generate database tree"}), 500

if __name__ == '__main__':
    app.run(debug=True)