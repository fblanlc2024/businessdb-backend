from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, verify_jwt_in_request
from flask_jwt_extended.exceptions import JWTExtendedException
import logging
from flask_limiter import RateLimitExceeded
from flask import jsonify
from app import redis_client, limiter

account_routes_bp = Blueprint('account_routes', __name__)

from ..classes.native.native_auth import NativeAuth

logging.basicConfig(level=logging.INFO)

# Create
@account_routes_bp.route('/account', methods=['POST'])
def create_account():
    data = request.json
    username = data['username']
    password = data['password']
    return NativeAuth.create_account(username, password)

# Update
@account_routes_bp.route('/account', methods=['PUT'])
def update_account():
    data = request.json
    username = data['username']
    password = data['password'] 
    new_username = data.get('new_username')
    new_password = data.get('new_password')

    return NativeAuth.update_account(username, password, new_username, new_password)

# Delete
@account_routes_bp.route('/account', methods=['DELETE'])
def delete_account():
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
            current_app.logger.error("User not found")
            return jsonify({"error": "User not found"}), 401
    data = request.json
    username = data['username']

    return NativeAuth.delete_account(username)

# Reset password only (different from other put method, which resets username and password)
@account_routes_bp.route('/reset_password', methods=['PUT'])
def reset_password():
    data = request.json
    username = data['username']
    new_password = data.get('new_password')

    return NativeAuth.reset_password(username, new_password)

@account_routes_bp.route('/protected', methods=['GET'])
def protected():
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

    return NativeAuth.protected(current_user)
    
@account_routes_bp.route('/token_login_set', methods=['POST'])
@limiter.limit("75 per 3 minutes")
def token_login():
    client_ip = request.remote_addr
    data = request.json
    username = data.get('username')
    password = data.get('password')

    logging.info(f"Login attempt for username: {username} from IP: {client_ip}")

    key = f"login_attempts:{client_ip}:{username}"
    expiry_key = f"username_expiry:{username}"

    return NativeAuth.token_login(client_ip, username, password, key, expiry_key)
    
# Rolling Refresh Token System
@account_routes_bp.route('/token_refresh', methods=['POST'])
def refresh_token():
    # Extract CSRF token from headers
    received_csrf_token = request.headers.get('X-CSRF-TOKEN')
    # current_app.logger.info("CSRF TOKEN THAT WAS FOUND: %s", received_csrf_token)
    
    if not received_csrf_token:
        current_app.logger.error("CSRF token missing in headers.")
        return jsonify({'message': 'CSRF token missing'}), 403

    # Ensure that the JWT exists and is valid
    verify_jwt_in_request(refresh=True)
    
    # Extract CSRF token from the current JWT
    jwt_data = get_jwt()
    stored_csrf_token = jwt_data.get('csrf')

    current_user = get_jwt_identity()

    return NativeAuth.refresh_token(received_csrf_token, stored_csrf_token, current_user)
    
@account_routes_bp.errorhandler(RateLimitExceeded)
def handle_rate_limit_error(e):
    client_ip = request.remote_addr
    ip_rate_limit_key = f"ip_rate_limit:{client_ip}"

    # Check if a lockout key already exists for this IP
    if not redis_client.exists(ip_rate_limit_key):
        redis_client.set(ip_rate_limit_key, 1, ex=3600)
        logging.info(f"Set a 1-hour rate limit lockout for IP: {client_ip}")

    return jsonify({'error': 'Rate limit exceeded. Please try again in 1 hour.'}), 429