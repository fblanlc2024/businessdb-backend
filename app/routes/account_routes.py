from flask import Blueprint, jsonify, request, current_app, redirect, url_for, make_response
import pymongo
from pymongo import MongoClient
from pymongo.errors import WriteError
import bcrypt
from flask_jwt_extended import (jwt_required, create_access_token, 
                                create_refresh_token, get_jwt_identity, 
                                get_jwt, verify_jwt_in_request, get_csrf_token)
from flask_jwt_extended.exceptions import JWTExtendedException
import logging
import datetime
import jwt
from flask_limiter import RateLimitExceeded

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from flask import Flask
from flask import jsonify

from app import client, db
from app.models import Account
from app import redis_client, limiter

account_routes_bp = Blueprint('account_routes', __name__)

accounts_collection = db.accounts
refresh_tokens_collection = db.refresh_tokens
ip_attempts_collection = db.ip_attempts
username_attempts_collection = db.username_attempts

MAX_LOGIN_ATTEMPTS = 5  # Maximum allowed attempts
LOGIN_ATTEMPT_WINDOW = 900  # 1 hour window for rate limiting

logging.basicConfig(level=logging.INFO)

# Create
@account_routes_bp.route('/account', methods=['POST'])
def create_account():
    data = request.json
    username = data['username']
    password = data['password']

    existing_user = accounts_collection.find_one({'username': username})
    if existing_user:
        return jsonify({'message': 'Username already exists'}), 400

    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(15))
    new_account = Account(username, hashed_pw, isAdmin=False)
    accounts_collection.insert_one(new_account.to_dict())

    return jsonify({'message': 'Account created successfully'}), 201

# Update
@account_routes_bp.route('/account', methods=['PUT'])
def update_account():
    data = request.json
    username = data['username']
    new_username = data.get('new_username')
    new_password = data.get('new_password')

    # Google users cannot modify their accounts
    if db.google_accounts.find_one({'account_name': username}):
        return jsonify({'message': 'Updates not allowed for users logged in with Google'}), 403

    account = accounts_collection.find_one({'username': username})
    if not account:
        return jsonify({'message': 'Account not found'}), 404

    updates = {}
    if new_username:
        updates['username'] = new_username
    if new_password:
        hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(15))
        updates['password_hash'] = hashed_pw

    accounts_collection.update_one({'username': username}, {'$set': updates})
    return jsonify({'message': 'Account updated successfully'}), 200

# Delete
@account_routes_bp.route('/account', methods=['DELETE'])
def delete_account():
    data = request.json
    username = data['username']

    # users cannot delete their Google accounts
    if db.google_accounts.find_one({'account_name': username}):
        return jsonify({'message': 'Deletion not allowed for users logged in with Google'}), 403

    result = accounts_collection.delete_one({'username': username})
    if result.deleted_count == 0:
        return jsonify({'message': 'Account not found'}), 404
    return jsonify({'message': 'Account deleted successfully'}), 200

# Reset password only (different from other put method, which resets username and password)
@account_routes_bp.route('/reset_password', methods=['PUT'])
def reset_password():
    data = request.json
    username = data['username']
    new_password = data.get('new_password')

    # Google users cannot modify their accounts
    if db.google_accounts.find_one({'account_name': username}):
        return jsonify({'message': 'Updates not allowed for users logged in with Google'}), 403

    account = accounts_collection.find_one({'username': username})
    if not account:
        return jsonify({'message': 'Account not found'}), 404

    if not new_password:
        return jsonify({'message': 'New password is required'}), 400

    hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(15))
    accounts_collection.update_one({'username': username}, {'$set': {'password_hash': hashed_pw}})
    return jsonify({'message': 'Password updated successfully'}), 200

@account_routes_bp.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    try:
        # current_app.logger.info(f"Received headers (Protected Route): {request.headers}")
        current_user = get_jwt_identity()
        # current_app.logger.info(f"[Protected Endpoint] - Current User: {current_user}")
        
        account = accounts_collection.find_one({'username': current_user})
        if not account:
            current_app.logger.error(f"[Protected Endpoint] - Account not found for username: {current_user}")
            return jsonify({'message': 'Account not found'}), 404
        
        user_id = str(account['_id'])
        return jsonify(logged_in_as=current_user, id=user_id), 200
    except Exception as e:
        current_app.logger.error(f"JWT verification error: {e}")
        current_app.logger.error(f"Error encountered: {str(e)}")
        current_app.logger.error(f"Request headers at the time of error: {request.headers}")
        current_app.logger.error(f"Request cookies at the time of error: {request.cookies}")
        return jsonify({'message': 'Token verification failed'}), 401
    
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

    account = accounts_collection.find_one({'username': username})
    if not account or not bcrypt.checkpw(password.encode('utf-8'), account['password_hash']):
        attempts = redis_client.incr(key)
        redis_client.expire(key, LOGIN_ATTEMPT_WINDOW)

        if attempts >= MAX_LOGIN_ATTEMPTS:
            # Check if the expiry timestamp is already set for this username
            if not redis_client.exists(expiry_key):
                expiry_timestamp = datetime.utcnow() + timedelta(minutes=15)
                redis_client.set(expiry_key, expiry_timestamp.strftime('%Y-%m-%d %H:%M:%S'), ex=900)

            remaining_minutes = calculate_remaining_minutes(username)
            return jsonify({'error': 'Too many login attempts. Please wait.', 'wait_minutes': remaining_minutes}), 429

        remaining_attempts = calculate_remaining_attempts(client_ip, username)
        return jsonify({'message': 'Incorrect username or password', 'remaining_attempts': remaining_attempts}), 401
    
    if bcrypt.checkpw(password.encode('utf-8'), account['password_hash']):
        access_token = create_access_token(identity=username)
        
        existing_refresh_token = refresh_tokens_collection.find_one({'userId': username})
        if existing_refresh_token:
            refresh_token = existing_refresh_token['token']
        else:
            refresh_token = create_refresh_token(identity=username)
            refresh_tokens_collection.insert_one({
                "token": refresh_token,
                "userId": username,
                "expiresAt": datetime.utcnow() + timedelta(days=30)
            })
            logging.info(f"Created new refresh token for username: {username}")

        is_admin = account.get('isAdmin', False)
        access_csrf = get_csrf_token(access_token)
        refresh_csrf = get_csrf_token(refresh_token)

        response_data = {
            'message': 'Login successful',
            'user': {'_id': str(account['_id']), 'username': account['username']},
            'csrf_tokens': {
                'access_csrf': access_csrf,
                'refresh_csrf': refresh_csrf
            }
        }
        response = make_response(jsonify(response_data))
        
        access_expiration_time = timedelta(days=1)
        refresh_expiration_time = timedelta(days=30)
        
        response.set_cookie('access_token_cookie', value=access_token, httponly=True, max_age=access_expiration_time, samesite='None', secure=True)
        response.set_cookie('refresh_token_cookie', value=refresh_token, httponly=True, max_age=refresh_expiration_time, samesite='None', secure=True)
        
        logging.info(f"User {username} logged in successfully.")
        return response
    
# Rolling Refresh Token System
@account_routes_bp.route('/token_refresh', methods=['POST'])
def refresh_token():
    try:
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

        # Compare the received CSRF token with the stored CSRF token
        if received_csrf_token != stored_csrf_token:
            current_app.logger.error("Invalid CSRF token.")
            return jsonify({'message': 'Invalid CSRF token'}), 403

        current_user = get_jwt_identity()

        account = accounts_collection.find_one({'username': current_user})
        is_admin = account.get('isAdmin', False)

        # Extract the old refresh token from the cookie
        old_refresh_token = request.cookies.get('refresh_token_cookie')
        token_data = refresh_tokens_collection.find_one({"token": old_refresh_token})

        if token_data:
            current_app.logger.info(f"Refresh token data: {token_data}")
        else:
            current_app.logger.error("Invalid or expired refresh token used.")

            return jsonify({'message': 'Invalid refresh token'}), 401
        if not old_refresh_token:
            return jsonify({'message': 'Refresh token missing'}), 401

        # Validate the old refresh token
        token_data = refresh_tokens_collection.find_one({"token": old_refresh_token})
        if not token_data:
            return jsonify({'message': 'Invalid refresh token'}), 401

        # Generate new tokens
        new_access_token = create_access_token(identity=current_user)
        new_refresh_token = create_refresh_token(identity=current_user)

        # Replace the old refresh token in the database
        refresh_tokens_collection.find_one_and_replace(
            {"token": old_refresh_token},
            {"token": new_refresh_token, "userId": current_user, "expiresAt": datetime.utcnow() + timedelta(days=30)}
        )

        # Generate new CSRF tokens for the new access and refresh tokens
        new_access_csrf = get_csrf_token(new_access_token)
        new_refresh_csrf = get_csrf_token(new_refresh_token)

        # Create response with new tokens in cookies and CSRF tokens in the response body
        response_data = {
            'message': 'Token refreshed successfully',
            'csrf_tokens': {
                'access_csrf': new_access_csrf,
                'refresh_csrf': new_refresh_csrf
            }
        }

        # current_app.logger.info(f"[Token Refresh] - Response Data: {response_data}")

        response = make_response(jsonify(response_data))

        access_expiration_time = timedelta(hours=1)
        refresh_expiration_time = timedelta(days=30)

        response.set_cookie('access_token_cookie', value=new_access_token, httponly=True, max_age=access_expiration_time.total_seconds(), samesite='None', secure=True)
        response.set_cookie('refresh_token_cookie', value=new_refresh_token, httponly=True, max_age=refresh_expiration_time.total_seconds(), samesite='None', secure=True)

        return response

    except JWTExtendedException as e:
        # Check if the exception is due to token expiration
        if 'Token has expired' in str(e):
            current_app.logger.error("User token has expired.")
        else:
            current_app.logger.error(f"JWT Error in /token_refresh: {e}")

        return jsonify({'message': str(e)}), 401
    
def is_rate_limit_exceeded(ip, username):
    current_time = datetime.utcnow()
    
    ip_record = ip_attempts_collection.find_one({'ip': ip})
    if ip_record and ip_record['last_attempt_time'] + timedelta(days=1) > current_time and ip_record['attempt_count'] >= 50:
        return True

    username_record = username_attempts_collection.find_one({'username': username})
    if username_record and username_record['last_attempt_time'] + timedelta(hours=1) > current_time and username_record['attempt_count'] >= 5:
        return True

    return False

def calculate_remaining_attempts(ip, username):
    key = f"login_attempts:{ip}:{username}"
    attempts = redis_client.get(key)

    if not attempts:
        return MAX_LOGIN_ATTEMPTS
    
    attempts_left = MAX_LOGIN_ATTEMPTS - int(attempts)
    return max(attempts_left, 0)

def calculate_remaining_minutes(username):
    try:
        expiry_key = f"username_expiry:{username}"
        expiry_timestamp = redis_client.get(expiry_key)

        current_time = datetime.utcnow()
        logging.info(f"Current time for username {username}: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")

        if expiry_timestamp:
            expiry_time = datetime.strptime(expiry_timestamp.decode(), '%Y-%m-%d %H:%M:%S')
            logging.info(f"Expiry time for username {username}: {expiry_time.strftime('%Y-%m-%d %H:%M:%S')}")

            if current_time > expiry_time:
                redis_client.delete(expiry_key)  # Purge the expired timestamp
                return 0

            remaining_time = expiry_time - current_time
            remaining_minutes = max(0, int(remaining_time.total_seconds() / 60))
            return remaining_minutes
        else:
            logging.info(f"No expiry time set for username {username}, no rate limit in effect.")
            return 0  # No expiry time set, no rate limit in effect
    except Exception as e:
        logging.error(f"Error in calculate_remaining_minutes for username {username}: {e}")
        return 0
    
@account_routes_bp.errorhandler(RateLimitExceeded)
def handle_rate_limit_error(e):
    client_ip = request.remote_addr
    ip_rate_limit_key = f"ip_rate_limit:{client_ip}"

    # Check if a lockout key already exists for this IP
    if not redis_client.exists(ip_rate_limit_key):
        redis_client.set(ip_rate_limit_key, 1, ex=3600)
        logging.info(f"Set a 1-hour rate limit lockout for IP: {client_ip}")

    return jsonify({'error': 'Rate limit exceeded. Please try again in 1 hour.'}), 429
