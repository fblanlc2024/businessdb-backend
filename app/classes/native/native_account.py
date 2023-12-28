from flask import request, current_app
import bcrypt
from flask_jwt_extended.exceptions import JWTExtendedException
import logging
import datetime

from datetime import datetime

from .native_auth import RateLimitException, AuthenticationException, InvalidTokenException

MAX_LOGIN_ATTEMPTS = 5 
LOGIN_ATTEMPT_WINDOW = 900

class NativeAccount:
    def __init__(self, username, password_hash, isAdmin=False):
        self.username = username
        self.password_hash = password_hash
        self.isAdmin = isAdmin
        self.created_at = datetime.datetime.utcnow()
        self.updated_at = datetime.datetime.utcnow()

        # For account locking - may be used by admins later and we have to implement this
        self.is_locked = False
        self.locked_until = None

    def to_dict(self):
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "isAdmin": self.isAdmin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_locked": self.is_locked,
            "locked_until": self.locked_until
        }
    
    def create_account(username, password, account_dal):
        existing_user = account_dal.find_account(username)
        if existing_user:
            return {'error': 'Username already exists', 'status': 400}

        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(15))
        new_account = NativeAccount(username, hashed_pw, isAdmin=False)
        account_dal.create_account(new_account.to_dict())

        return {'message': 'Account created successfully', 'status': 201}

    def update_account(username, new_username, new_password, account_dal):
        # Google users cannot modify their accounts
        if account_dal.is_google_account(username):
            return {'message': 'Updates not allowed for users logged in with Google', 'status': 403}

        account = account_dal.find_account(username)
        if not account:
            return {'message': 'Account not found', 'status': 404}

        updates = {}
        if new_username:
            updates['username'] = new_username
        if new_password:
            hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(15))
            updates['password_hash'] = hashed_pw

        account_dal.update_account(username, updates)
        return {'message': 'Account updated successfully', 'status': 200}
    
    def delete_account(username, account_dal):
        # Google users cannot delete their accounts
        if account_dal.is_google_account(username):
            return {'message': 'Deletion not allowed for users logged in with Google', 'status': 403}

        result = account_dal.delete_account(username)
        if result.deleted_count == 0:
            return {'message': 'Account not found', 'status': 404}
        
        return {'message': 'Account deleted successfully', 'status': 200}
    
    def reset_password(username, new_password, account_dal):
        # Google users cannot modify their accounts
        if account_dal.is_google_account():
            return {'message': 'Updates not allowed for users logged in with Google', 'status': 403}

        account = account_dal.find_account(username)
        if not account:
            return {'message': 'Account not found', 'status': 404}

        if not new_password:
            return {'message': 'New password is required', 'status': 400}

        hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(15))
        account_dal.update_password(username, hashed_pw)
        return {'message': 'Password updated successfully', 'status': 200}
    
    def protected(current_user, account_dal):
        try:
            account = account_dal.find_account(current_user)

            if not account:
                current_app.logger.error(f"[Protected Endpoint] - Account not found for username: {current_user}")
                return {'error': 'Account not found', 'status': 404}
            
            user_id = str(account['_id'])
            return {'message': 'Account details retrieved successfully', 'data': {'logged_in_as': current_user, 'id': user_id}, 'status': 200}
        except Exception as e:
            current_app.logger.error(f"JWT verification error: {e}")
            current_app.logger.error(f"Error encountered: {str(e)}")
            current_app.logger.error(f"Request headers at the time of error: {request.headers}")
            current_app.logger.error(f"Request cookies at the time of error: {request.cookies}")
            return {'error': 'Token verification failed', 'status': 401}


    def token_login(client_ip, username, password, native_auth):
        try:
            logging.info(f"Login attempt for username: {username} from IP: {client_ip}")
            native_auth.check_rate_limiting(client_ip, username)
            account = native_auth.authenticate_user(username, password)
            access_token, refresh_token = native_auth.generate_tokens(username)
            current_app.logger.info(f"Access token: {access_token}")
            current_app.logger.info(f"Refresh Token: {refresh_token}")
            return native_auth.create_login_response(username, account, access_token, refresh_token)
        except RateLimitException as e:
            return {'error': 'Too many login attempts. Please wait.', 'wait_minutes': e.remaining_minutes, 'status': 429}
        except AuthenticationException as e:
            return {'error': 'Incorrect username or password', 'remaining_attempts': e.remaining_attempts, 'status': 401}
        
    def refresh_token(received_csrf_token, old_refresh_token, current_user, native_auth):
        try:
            logging.info(f"Attempting to refresh token for user: {current_user}")
            native_auth.validate_old_refresh_token(old_refresh_token)
            new_access_token, new_refresh_token = native_auth.generate_new_tokens(current_user)
            native_auth.update_refresh_token_in_db(old_refresh_token, new_refresh_token, current_user)
            response = native_auth.create_refresh_token_response(new_access_token, new_refresh_token)
            logging.info(f"Refresh token successful for {current_user}. New Access Token: {new_access_token}, New Refresh Token: {new_refresh_token}")
            return response
        except InvalidTokenException as e:
            logging.error(f"Invalid refresh token for {current_user}. Error: {str(e)}")
            return {'error': 'Invalid refresh token', 'status': 401}
        except JWTExtendedException as e:
            logging.error(f"JWT error for {current_user}. Error: {str(e)}")
            return {'error': str(e), 'status': 401}