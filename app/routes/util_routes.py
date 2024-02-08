from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
import logging
from bson import ObjectId

util_routes_bp = Blueprint("util_routes", __name__)
from app import db

accounts_collection = db.accounts
google_accounts_collection = db.google_accounts

@util_routes_bp.route('/admin_status_check', methods=['GET'])
def admin_status_check():
    try:
        # Attempt to authenticate with JWT in Authorization header
        verify_jwt_in_request()
        current_user = get_jwt_identity()
        current_app.logger.info(f"current_user for admin status check: {current_user}")
        logging.info(f"JWT authentication successful for user: {current_user}")
        is_admin = is_user_admin(current_user, accounts_collection, google_accounts_collection)

        # Use is_user_admin to check admin status
        if is_admin == True:
            return jsonify({"isAdmin": True}), 200
        elif is_admin == False:
            return jsonify({"isAdmin": False}), 200
    except Exception as e:
        logging.warning(f"JWT authentication failed: {e}")

    oauth_token = request.cookies.get('access_token_cookie')
    logging.info(f"OAuth token from cookie: {oauth_token}")

    if oauth_token:
        # Use is_user_admin to check admin status with OAuth token
        if is_user_admin(oauth_token, accounts_collection, google_accounts_collection):
            return jsonify({"isAdmin": True}), 200
        else:
            logging.warning("No user found with the provided OAuth token")

    logging.error("User not authenticated")
    return jsonify({"error": "User not authenticated"}), 401

def is_user_admin(identifier, accounts_collection, google_accounts_collection):
    current_app.logger.info(f"Checking admin status for identifier: {identifier}")

    # Convert the identifier to ObjectId
    try:
        object_id = ObjectId(identifier)
    except:
        object_id = None

    # Check for the user in the native accounts collection by username, user_id, or _id
    user_document = accounts_collection.find_one({
        "$or": [
            {"username": identifier},
            {"_id": object_id}
        ]
    })
    if user_document:
        return user_document.get("isAdmin", False)

    # If not found, check in the Google accounts collection by access token, user_id, or _id
    user_document = google_accounts_collection.find_one({
        "$or": [
            {"access_token": identifier},
            {"user_id": identifier},
            {"_id": object_id}
        ]
    })
    if user_document:
        return user_document.get("isAdmin", False)

    # If the user is not found in either collection
    return jsonify({"error": "User not found"}), 401