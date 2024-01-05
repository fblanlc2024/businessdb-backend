from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from flask import jsonify

from app import db
from .util_routes import is_user_admin
from ..classes.business.data_handling import DataHandler

businesses_collection = db.businesses
counters_collection = db.counters
accounts_collection = db.accounts
google_accounts_collection = db.google_accounts

data_routes_bp = Blueprint('data_routes', __name__)

@data_routes_bp.route('/api/businesses', methods=['GET'])
def get_businesses():
    return DataHandler.get_businesses()

@data_routes_bp.route('/api/business_info', methods=['GET'])
def get_business_info():
    # Attempt JWT authentication
    try:
        verify_jwt_in_request()
        current_user = get_jwt_identity()
    except Exception as jwt_error:
        current_app.logger.warning(f"JWT authentication failed: {jwt_error}")

        # Fallback to OAuth token
        oauth_token = request.cookies.get('access_token_cookie')
        current_app.logger.info(f"OAuth token from cookie: {oauth_token}")
        if oauth_token:
            current_user = oauth_token
        else:
            current_app.logger.error("User not authenticated")
            return jsonify({"error": "User not authenticated"}), 401

    # Check if the user is an admin
    is_admin = is_user_admin(current_user, accounts_collection, google_accounts_collection)
    current_app.logger.info(f"admin status for business info check: {is_admin}")

    business_name = request.args.get('name')
    return DataHandler.get_business_info(business_name, is_admin)


@data_routes_bp.route('/add_business', methods=['POST'])
def add_business():
    data = request.json
    
    return DataHandler.add_business(data)

@data_routes_bp.route('/delete_business/<int:business_id>', methods=['DELETE'])
def delete_business_by_id(business_id):
    return DataHandler.delete_business_by_id(business_id)
    
@data_routes_bp.route('/autocomplete', methods=['GET'])
def autocomplete():
    query = request.args.get('query')
    return DataHandler.autocomplete(query)

@data_routes_bp.route('/edit_business_info', methods=['POST'])
def edit_business_info():
    csrf_token = request.headers.get('X-CSRF-TOKEN')
    current_app.logger.info(f"CSRF Token: {csrf_token}")

    # Attempt to verify JWT
    try:
        verify_jwt_in_request()
        current_user = get_jwt_identity()
    except Exception as jwt_error:
        current_app.logger.warning(f"JWT authentication failed: {jwt_error}")

        # Fallback to OAuth token
        oauth_token = request.cookies.get('access_token_cookie')
        current_app.logger.info(f"OAuth token from cookie: {oauth_token}")
        if oauth_token:
            current_user = oauth_token
        else:
            current_app.logger.error("User not authenticated")
            return jsonify({"error": "User not authenticated"}), 401

    # Check if the user is an admin
    if not is_user_admin(current_user, accounts_collection, google_accounts_collection):
        return jsonify({"error": "Unauthorized access"}), 403

    data = request.json
    business_id = data['business_id']
    business_info = data['business_info']

    return DataHandler.edit_business_info(business_id, business_info)

@data_routes_bp.route('/add_address/<int:business_id>', methods=['POST'])
@jwt_required()
def add_address(business_id):
    try:
        verify_jwt_in_request()
        current_user = get_jwt_identity()
    except Exception as jwt_error:
        current_app.logger.warning(f"JWT authentication failed: {jwt_error}")

        # Fallback to OAuth token
        oauth_token = request.cookies.get('access_token_cookie')
        current_app.logger.info(f"OAuth token from cookie: {oauth_token}")
        if oauth_token:
            current_user = oauth_token
        else:
            current_app.logger.error("User not authenticated")
            return jsonify({"error": "User not authenticated"}), 401
        
    if not is_user_admin(current_user, accounts_collection, google_accounts_collection):
        return jsonify({"error": "Unauthorized access"}), 403
    
    data = request.json
    address_data = data['address']
    return DataHandler.add_business_address(business_id, address_data)
