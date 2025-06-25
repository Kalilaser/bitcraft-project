from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import db_helpers

app = Flask(__name__)
CORS(app)

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    # Get all items in the inventory as a list of dicts
    conn = db_helpers.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT ItemName, Tier, Quantity, Category, Source, IsCraftable, Notes FROM Inventory')
    rows = cursor.fetchall()
    conn.close()

    # Convert each row to a dictionary
    inventory = []
    for row in rows:
        inventory.append({
            "ItemName": row[0],
            "Tier": row[1],
            "Quantity": row[2],
            "Category": row[3],
            "Source": row[4],
            "IsCraftable": bool(row[5]),
            "Notes": row[6]
        })

    return jsonify(inventory)

@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    conn = db_helpers.get_db_connection()
    cursor = conn.cursor()
    # Get all recipes
    cursor.execute('SELECT RecipeID, RecipeName, OutputItem, OutputQty, IsShaped, Notes FROM Recipes')
    recipes = []
    for row in cursor.fetchall():
        recipe_id = row[0]
        # Get ingredients for this recipe
        cursor.execute('SELECT InputItem, Quantity FROM Ingredients WHERE RecipeID = ?', (recipe_id,))
        ingredients = [{"InputItem": ing[0], "Quantity": ing[1]} for ing in cursor.fetchall()]
        recipes.append({
            "RecipeID": row[0],
            "RecipeName": row[1],
            "OutputItem": row[2],
            "OutputQty": row[3],
            "IsShaped": bool(row[4]),
            "Notes": row[5],
            "Ingredients": ingredients
        })
    conn.close()
    return jsonify(recipes)

@app.route('/api/inventory/<item_name>/<tier>', methods=['PATCH'])
def update_inventory(item_name, tier):
    data = request.get_json()
    new_quantity = data.get("Quantity")
    conn = db_helpers.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE Inventory SET Quantity = ? WHERE ItemName = ? AND Tier = ?
    ''', (new_quantity, item_name, tier))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "item": item_name, "tier": tier, "new_quantity": new_quantity})

@app.route('/api/inventory', methods=['POST'])
def add_inventory():
    data = request.get_json()
    db_helpers.add_inventory_item(
        data["ItemName"], data["Tier"], data["Category"],
        data["IsCraftable"], data.get("Source", ""), data.get("Notes", "")
    )
    return jsonify({"success": True, "item": data["ItemName"]})

@app.route('/api/recipes', methods=['POST'])
def add_recipe():
    data = request.get_json()
    recipe_id = db_helpers.add_recipe(
        data["RecipeName"], data["OutputItem"], data["OutputQty"],
        data.get("IsShaped", False), data.get("Notes", "")
    )
    if recipe_id:
        db_helpers.add_ingredients(recipe_id, data["Ingredients"])
    return jsonify({"success": bool(recipe_id), "RecipeID": recipe_id})

@app.route('/api/tree', methods=['POST'])
def get_tree():
    data = request.get_json()
    item = data["ItemName"]
    qty = data.get("Quantity", 1)
    tree = db_helpers.get_full_tree(item, qty)
    shopping_list = db_helpers.flatten_tree_to_shopping_list(tree)
    return jsonify({"tree": tree, "shopping_list": shopping_list})

@app.route('/api/projects', methods=['GET'])
def get_projects():
    conn = db_helpers.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT ProjectID, Name, Description, CreatedAt FROM Projects')
    projects = []
    for row in cursor.fetchall():
        projects.append({
            "ProjectID": row[0],
            "Name": row[1],
            "Description": row[2],
            "CreatedAt": row[3]
        })
    conn.close()
    return jsonify(projects)

# Create a new project
@app.route('/api/projects', methods=['POST'])
def create_project():
    data = request.get_json()
    name = data["Name"]
    description = data.get("Description", "")
    conn = db_helpers.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO Projects (Name, Description) VALUES (?, ?)', (name, description))
    project_id = cursor.lastrowid
    # Add project items if provided
    items = data.get("Items", [])
    for item in items:
        cursor.execute('''
            INSERT INTO ProjectItems (ProjectID, ItemName, Tier, Quantity)
            VALUES (?, ?, ?, ?)
        ''', (project_id, item["ItemName"], item.get("Tier", ""), item["Quantity"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "ProjectID": project_id})

# Get one project's details (items, tree, shopping list)
@app.route('/api/project/<int:project_id>', methods=['GET'])
def get_project(project_id):
    conn = db_helpers.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT Name, Description, CreatedAt FROM Projects WHERE ProjectID = ?', (project_id,))
    proj_row = cursor.fetchone()
    if not proj_row:
        conn.close()
        return jsonify({"error": "Project not found"}), 404

    cursor.execute('SELECT ItemName, Tier, Quantity FROM ProjectItems WHERE ProjectID = ?', (project_id,))
    items = [{"ItemName": r[0], "Tier": r[1], "Quantity": r[2]} for r in cursor.fetchall()]

    # For demo: get the tree and shopping list for all project items
    all_trees = []
    all_shopping = {}
    for i in items:
        tree = db_helpers.get_full_tree(i["ItemName"], i["Quantity"])
        all_trees.append({i["ItemName"]: tree})
        slist = db_helpers.flatten_tree_to_shopping_list(tree)
        for k, v in slist.items():
            all_shopping[k] = all_shopping.get(k, 0) + v

    conn.close()
    return jsonify({
        "ProjectID": project_id,
        "Name": proj_row[0],
        "Description": proj_row[1],
        "CreatedAt": proj_row[2],
        "Items": items,
        "AllTrees": all_trees,
        "ShoppingList": all_shopping
    })

@app.route('/api/inventory/<item_name>/<tier>', methods=['DELETE'])
def delete_inventory(item_name, tier):
    conn = db_helpers.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM Inventory WHERE ItemName = ? AND Tier = ?', (item_name, tier))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/recipes/<int:recipe_id>', methods=['DELETE'])
def delete_recipe(recipe_id):
    conn = db_helpers.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM Ingredients WHERE RecipeID = ?', (recipe_id,))
    cursor.execute('DELETE FROM Recipes WHERE RecipeID = ?', (recipe_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    conn = db_helpers.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM ProjectItems WHERE ProjectID = ?', (project_id,))
    cursor.execute('DELETE FROM Projects WHERE ProjectID = ?', (project_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route('/api/tree', methods=['GET'])
def get_full_database_tree():
    # Return a tree/graph of all recipes for visualization (advanced/future)
    conn = db_helpers.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT OutputItem FROM Recipes')
    all_items = [r[0] for r in cursor.fetchall()]
    conn.close()
    all_trees = {}
    for item in all_items:
        all_trees[item] = db_helpers.get_full_tree(item, 1)
    return jsonify(all_trees)

if __name__ == '__main__':
    app.run(debug=True)