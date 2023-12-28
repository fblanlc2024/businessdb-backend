from flask import Blueprint, jsonify, request, make_response, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from flask_limiter import RateLimitExceeded

from app import db
from app import redis_client, limiter
from ..classes.native.native_account import NativeAccount
from ..classes.native.native_account_dal import NativeAccountDAL
from ..classes.native.native_auth import NativeAuth
from ..classes.redis.redis_layer import RedisLayer

account_routes_bp = Blueprint('account_routes', __name__)

account_dal = NativeAccountDAL(db)
redis_layer = RedisLayer(redis_client)
native_auth = NativeAuth(account_dal, redis_layer)

logging.basicConfig(level=logging.INFO)

# Create
@account_routes_bp.route('/account', methods=['POST'])
def create_account_route():
    data = request.json
    username = data['username']
    password = data['password']

    result = NativeAccount.create_account(
        username,
        password,
        account_dal
    )

    return create_response(result)

# Update
@account_routes_bp.route('/account', methods=['PUT'])
def update_account():
    data = request.json
    username = data['username']
    new_username = data['new_username']
    new_password = data['new_password']

    result = NativeAccount.update_account(
        username,
        new_username,
        new_password,
        account_dal
    )

    return create_response(result)

# Delete
@account_routes_bp.route('/account', methods=['DELETE'])
def delete_account():
    data = request.json
    username = data['username']

    result = NativeAccount.delete_account(
        username,
        account_dal = account_dal
    )

    return create_response(result)

# Reset password only (different from other put method, which resets username and password)
@account_routes_bp.route('/reset_password', methods=['PUT'])
def reset_password():
    data = request.json
    username = data['username']
    new_password = data['new_password']

    result = NativeAccount.reset_password(
        username,
        new_password,
        account_dal = account_dal
    )

    return create_response(result)


@account_routes_bp.route('/protected', methods=['GET'])
@jwt_required()
def protected_route():
    current_user = get_jwt_identity()
    result = NativeAccount.protected(
        current_user,
        account_dal
    )

    return create_response(result)
    
@account_routes_bp.route('/token_login_set', methods=['POST'])
@limiter.limit("75 per 3 minutes")
def token_login_route():
    client_ip = request.remote_addr
    data = request.json
    username = data['username']
    password = data['password']

    result = NativeAccount.token_login(
        client_ip,
        username,
        password,
        native_auth
    )

    cookies = result.pop('cookies', None)

    return create_response(result, cookies=cookies)
    
# Rolling Refresh Token System
@account_routes_bp.route('/token_refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh_token_route():
    received_csrf_token = request.headers.get('X-CSRF-TOKEN')
    old_refresh_token = request.cookies.get('refresh_token_cookie')
    logging.info(f"Received refresh token cookie: {old_refresh_token}")
    current_user = get_jwt_identity()
    
    result = NativeAccount.refresh_token(
        received_csrf_token,
        old_refresh_token,
        current_user
    )

    cookies = result.pop('cookies', None)

    return create_response(result, cookies=cookies)
    
@account_routes_bp.errorhandler(RateLimitExceeded)
def handle_rate_limit_error(e, redis_layer):
    client_ip = request.remote_addr

    if not redis_layer.is_ip_rate_limited(client_ip):
        redis_layer.set_ip_rate_limit(client_ip)

    return jsonify({'error': 'Rate limit exceeded. Please try again in 1 hour.'}), 429

def create_response(result, cookies=None):
    status_code = result.get('status', 200 if 'message' in result else 400)

    # Prepare the response body dynamically
    response_body = {key: value for key, value in result.items() if key not in ['status', 'cookies']}

    response = make_response(jsonify(response_body), status_code)

    # Set cookies if provided
    if cookies:
        for cookie_key, cookie_details in cookies.items():
            response.set_cookie(
                cookie_key,
                value=cookie_details['value'],
                max_age=cookie_details.get('max_age', None),
                httponly=cookie_details.get('httponly', True),
                samesite=cookie_details.get('samesite', 'None'),
                secure=cookie_details.get('secure', True)
            )

    return response
