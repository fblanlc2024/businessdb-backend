import bcrypt
from flask_jwt_extended import create_access_token, create_refresh_token, get_csrf_token
from flask import current_app

class NativeAuth:
    def __init__(self, account_dal, redis_layer):
        self.account_dal = account_dal
        self.redis_layer = redis_layer

    def check_rate_limiting(self, client_ip, username):
        attempts = self.redis_layer.increment_login_attempts(client_ip, username)
        if attempts >= self.redis_layer.MAX_LOGIN_ATTEMPTS:
            self.redis_layer.set_expiry_for_username(username)
            remaining_minutes = self.redis_layer.get_remaining_minutes(username)
            raise RateLimitException(remaining_minutes)

    def authenticate_user(self, username, password):
        account = self.account_dal.find_account(username)
        if not account or not bcrypt.checkpw(password.encode('utf-8'), account['password_hash']):
            raise AuthenticationException()

        return account

    def generate_tokens(self, username):
        access_token = create_access_token(identity=username)
        refresh_token = create_refresh_token(identity=username)
        return access_token, refresh_token

    def create_login_response(self, username, account, access_token, refresh_token):
        access_csrf = get_csrf_token(access_token)
        refresh_csrf = get_csrf_token(refresh_token)

        current_app.logger.info(f"Refresh CSRF: {refresh_csrf}")

        response_data = {
            'message': 'Login successful',
            'user': {'_id': str(account['_id']), 'username': account['username']},
            'csrf_tokens': {'access_csrf': access_csrf, 'refresh_csrf': refresh_csrf},
            'tokens': {'access_token': access_token, 'refresh_token': refresh_token},
            'status': 200,
            'cookies': {
                'access_token_cookie': {'value': access_token, 'max_age': 86400, 'httponly': True, 'samesite': 'None', 'secure': True},
                'refresh_token_cookie': {'value': refresh_token, 'max_age': 2592000, 'httponly': True, 'samesite': 'None', 'secure': True}
            }
        }
        return response_data
    
    def validate_old_refresh_token(self, old_refresh_token):
        token_data = self.account_dal.find_refresh_token(old_refresh_token)
        if not token_data:
            raise InvalidTokenException()

    def generate_new_tokens(self, current_user):
        new_access_token = create_access_token(identity=current_user)
        new_refresh_token = create_refresh_token(identity=current_user)
        return new_access_token, new_refresh_token

    def update_refresh_token_in_db(self, old_refresh_token, new_refresh_token, current_user):
        self.account_dal.replace_refresh_token(old_refresh_token, new_refresh_token, current_user)

    def create_refresh_token_response(self, access_token, refresh_token):
        new_access_csrf = get_csrf_token(access_token)
        new_refresh_csrf = get_csrf_token(refresh_token)

        response_data = {
            'message': 'Token refreshed successfully',
            'csrf_tokens': {'access_csrf': new_access_csrf, 'refresh_csrf': new_refresh_csrf},
            'tokens': {'access_token': access_token, 'refresh_token': refresh_token},
            'status': 200,
            'cookies': {
                'access_token_cookie': {'value': access_token, 'max_age': 3600, 'httponly': True, 'samesite': 'None', 'secure': True},
                'refresh_token_cookie': {'value': refresh_token, 'max_age': 2592000, 'httponly': True, 'samesite': 'None', 'secure': True}
            }
        }
        return response_data
    
class RateLimitException(Exception):
    def __init__(self, remaining_minutes):
        self.remaining_minutes = remaining_minutes
        super().__init__("Rate limit exceeded")

class AuthenticationException(Exception):
    def __init__(self, remaining_attempts):
        self.remaining_attempts = remaining_attempts
        super().__init__("Authentication failed")

class InvalidTokenException(Exception):
    def __init__(self):
        super().__init__("Invalid refresh token")