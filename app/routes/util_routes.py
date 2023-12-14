from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

util_routes_bp = Blueprint("util_routes", __name__)
from app import db

accounts_collection = db.accounts

@util_routes_bp.route('/admin_status_check', methods=['GET'])
@jwt_required()
def admin_status_check():
    current_user = get_jwt_identity()

    user_document = accounts_collection.find_one({"username": current_user})

    if user_document:
        is_admin = user_document.get("isAdmin", False)
        return jsonify({"isAdmin": is_admin}), 200
    else:
        return jsonify({"error": "User not found"}), 404
    
def is_user_admin(username, accounts_collection):
    user_document = accounts_collection.find_one({"username": username})
    if user_document:
        return user_document.get("isAdmin", False)
    else:
        raise ValueError("User not found")