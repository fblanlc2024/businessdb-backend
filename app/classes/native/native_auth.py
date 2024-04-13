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
from ...models.account import Account
from app import redis_client, limiter

accounts_collection = db.accounts
google_accounts_collection = db.google_accounts
refresh_tokens_collection = db.refresh_tokens

MAX_LOGIN_ATTEMPTS = 5  # Maximum allowed attempts
LOGIN_ATTEMPT_WINDOW = 900  # 1 hour window for rate limiting

class NativeAuth:
    def __init__(self):
        pass
    
    def create_account(username, password):
        existing_user = accounts_collection.find_one({'username': username})
        if existing_user:
            return jsonify({'message': 'Username already exists'}), 400

        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(15))
        new_account = Account(username, hashed_pw, isAdmin=False)
        accounts_collection.insert_one(new_account.to_dict())

        return jsonify({'message': 'Account created successfully'}), 201
    
    def update_account(username, password, new_username, new_password):
        if google_accounts_collection.find_one({'account_name': username}):
            return jsonify({'message': 'Updates not allowed for users logged in with Google'}), 403

        account = accounts_collection.find_one({'username': username})

        updates = {}
        if new_username:
            updates['username'] = new_username

        if new_password:
            if not bcrypt.checkpw(password.encode('utf-8'), account['password_hash']):
                return jsonify({'message': 'This is not the current password for this account'}), 403
            
            new_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(15))

            if bcrypt.checkpw(new_password.encode('utf-8'), account['password_hash']):
                return jsonify({'message': 'Please enter a new password'}), 400

            updates['password_hash'] = new_pw

        accounts_collection.update_one({'username': username}, {'$set': updates})
        return jsonify({'message': 'Account updated successfully'}), 200
    
    def delete_account(username):
        if google_accounts_collection.find_one({'account_name': username}):
            return jsonify({'message': 'Deletion not allowed for users logged in with Google'}), 403
        accounts_collection.delete_one({'username': username})
        return jsonify({'message': 'Account deleted successfully'}), 200
    
    def reset_password(username, new_password):
        if google_accounts_collection.find_one({'account_name': username}):
            return jsonify({'message': 'Updates not allowed for users logged in with Google'}), 403

        account = accounts_collection.find_one({'username': username})
        if not account:
            return jsonify({'message': 'Account not found'}), 404

        if not new_password:
            return jsonify({'message': 'New password is required'}), 400

        hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(15))
        accounts_collection.update_one({'username': username}, {'$set': {'password_hash': hashed_pw}})
        return jsonify({'message': 'Password updated successfully'}), 200
    
    # Checks credentials for certain routes
    def protected(current_user):
        csrf_token = request.headers.get('X-CSRF-TOKEN')
        current_app.logger.info(f"CSRF Token: {csrf_token}")
        
        try:
            account = accounts_collection.find_one({'username': current_user})
            if account:
                user_id = str(account['_id'])
                return jsonify(logged_in_as=current_user, id=user_id), 200
            else:
                current_app.logger.info(f"[Protected Endpoint] - Native account not found for username: {current_user}. Trying with OAuth...")

                oauth_token = request.cookies.get('access_token_cookie')
                if oauth_token:
                    user_document = google_accounts_collection.find_one({"access_token": oauth_token})
                    if user_document:
                        user_id = str(user_document['_id'])
                        return jsonify(logged_in_as=user_document['account_name']), 200
                    else:
                        current_app.logger.error("OAuth account not found")
                        return jsonify({'message': 'OAuth account not found'}), 401
                else:
                    current_app.logger.error("OAuth token not found")
                    return jsonify({'message': 'OAuth token not found'}), 401

        except Exception as e:
            current_app.logger.error(f"Error during authentication: {e}")
            current_app.logger.error(f"Request headers at the time of error: {request.headers}")
            current_app.logger.error(f"Request cookies at the time of error: {request.cookies}")
            return jsonify({'message': 'Authentication failed'}), 500
        
    # Token login that assigns access and refresh tokens as well as their CSRF counterparts
    def token_login(client_ip, username, password, key, expiry_key):

        logging.info(f"Login attempt for username: {username} from IP: {client_ip}")

        key = f"login_attempts:{client_ip}:{username}"
        expiry_key = f"username_expiry:{username}"

        account = accounts_collection.find_one({'username': username})
        if not account or not bcrypt.checkpw(password.encode('utf-8'), account['password_hash']):
            attempts = redis_client.incr(key)
            redis_client.expire(key, LOGIN_ATTEMPT_WINDOW)

            if attempts >= MAX_LOGIN_ATTEMPTS:
                if not redis_client.exists(expiry_key):
                    expiry_timestamp = datetime.utcnow() + timedelta(minutes=15)
                    redis_client.set(expiry_key, expiry_timestamp.strftime('%Y-%m-%d %H:%M:%S'), ex=900)

                remaining_minutes = NativeAuth.calculate_remaining_minutes(username)
                return jsonify({'error': 'Too many login attempts. Please wait.', 'wait_minutes': remaining_minutes}), 429

            remaining_attempts = NativeAuth.calculate_remaining_attempts(client_ip, username)
            return jsonify({'message': 'Incorrect username or password', 'remaining_attempts': remaining_attempts}), 401
        
        if bcrypt.checkpw(password.encode('utf-8'), account['password_hash']):
            access_token = create_access_token(identity=username)
            
            now = datetime.utcnow()
            existing_refresh_token = refresh_tokens_collection.find_one({'userId': username})
            if existing_refresh_token and existing_refresh_token['expiresAt'] > now:
                refresh_token = existing_refresh_token['token']
            else:
                refresh_token = create_refresh_token(identity=username)
                refresh_tokens_collection.update_one(
                    {'userId': username},
                    {
                        '$set': {
                            "token": refresh_token,
                            "expiresAt": now + timedelta(days=30)
                        },
                        '$setOnInsert': {
                            "userId": username
                        }
                    },
                    upsert=True
                )
                logging.info(f"Refresh token updated or created for username: {username}")

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
            response.set_cookie('access_csrf_cookie', value=access_csrf, httponly=True, max_age=access_expiration_time, samesite='None', secure=True)
            response.set_cookie('refresh_csrf_cookie', value=refresh_csrf, httponly=True, max_age=refresh_expiration_time, samesite='None', secure=True)
            
            logging.info(f"User {username} logged in successfully.")
            return response

    # Rolling refresh token system that replaces old refresh token with new one inside MongoDB. Each refresh token is only used once.
    def refresh_token(received_csrf_token, stored_csrf_token, current_user):
        try:
            if not received_csrf_token:
                current_app.logger.error("CSRF token missing in headers.")
                return jsonify({'message': 'CSRF token missing'}), 403

            if received_csrf_token != stored_csrf_token:
                current_app.logger.error("Invalid CSRF token.")
                return jsonify({'message': 'Invalid CSRF token'}), 403

            old_refresh_token = request.cookies.get('refresh_token_cookie')

            if not old_refresh_token:
                return jsonify({'message': 'Refresh token missing'}), 401

            token_data = refresh_tokens_collection.find_one({"token": old_refresh_token})
            if not token_data:
                return jsonify({'message': 'Invalid refresh token'}), 401

            new_access_token = create_access_token(identity=current_user)
            new_refresh_token = create_refresh_token(identity=current_user)

            refresh_tokens_collection.find_one_and_replace(
                {"token": old_refresh_token},
                {"token": new_refresh_token, "userId": current_user, "expiresAt": datetime.utcnow() + timedelta(days=30)}
            )

            new_access_csrf = get_csrf_token(new_access_token)
            new_refresh_csrf = get_csrf_token(new_refresh_token)

            response_data = {
                'message': 'Token refreshed successfully',
                'csrf_tokens': {
                    'access_csrf': new_access_csrf,
                    'refresh_csrf': new_refresh_csrf
                }
            }

            response = make_response(jsonify(response_data))

            access_expiration_time = timedelta(hours=1)
            refresh_expiration_time = timedelta(days=30)

            response.set_cookie('access_token_cookie', value=new_access_token, httponly=True, max_age=access_expiration_time.total_seconds(), samesite='None', secure=True)
            response.set_cookie('refresh_token_cookie', value=new_refresh_token, httponly=True, max_age=refresh_expiration_time.total_seconds(), samesite='None', secure=True)
            response.set_cookie('access_csrf_cookie', value=new_access_csrf, httponly=True, max_age=access_expiration_time.total_seconds(), samesite='None', secure=True)
            response.set_cookie('refresh_csrf_cookie', value=new_refresh_csrf, httponly=True, max_age=refresh_expiration_time.total_seconds(), samesite='None', secure=True)

            return response

        except JWTExtendedException as e:
            if 'Token has expired' in str(e):
                current_app.logger.error("User token has expired.")
                return jsonify({'message': 'Token has expired'}), 401
            else:
                current_app.logger.error(f"JWT Error in /token_refresh: {e}")
                return jsonify({'message': str(e)}), 401
        
    @staticmethod    
    def calculate_remaining_attempts(ip, username):
        key = f"login_attempts:{ip}:{username}"
        attempts = redis_client.get(key)

        if not attempts:
            return MAX_LOGIN_ATTEMPTS
        
        attempts_left = MAX_LOGIN_ATTEMPTS - int(attempts)
        return max(attempts_left, 0)

    # 15 minute timeout for 5 incorrect attempts, 1 hour timeout for general rate limiting
    @staticmethod
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