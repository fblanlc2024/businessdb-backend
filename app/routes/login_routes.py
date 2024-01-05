from flask import Blueprint, request, jsonify, current_app
from app import db
from app import redis_client

from ..classes.google.google_auth import GoogleAuth

login_routes_bp = Blueprint('login_routes_bp', __name__)
refresh_tokens_collection = db.refresh_tokens

@login_routes_bp.route("/login")
def login():
    client_ip = request.remote_addr
    ip_rate_limit_key = f"ip_rate_limit:{client_ip}"

    # Check rate limit
    if redis_client.exists(ip_rate_limit_key):
        return jsonify({'error': 'IP rate limit exceeded. Please try again later.'})
    
    return GoogleAuth.login()

@login_routes_bp.route("/login/callback")
def callback():
    state = request.cookies.get('state')
    return GoogleAuth.callback(state)

@login_routes_bp.route('/google_token_refresh', methods=['POST'])
def refresh_token():
    try:
        refresh_token = request.cookies.get('refresh_token_cookie')
        if not refresh_token:
            return jsonify({'message': 'Refresh token not found'}), 401

        return GoogleAuth.refresh_token(refresh_token)

    except Exception as e:
        return jsonify({'message': str(e)}), 500

@login_routes_bp.route('/google_user_data')
def google_user_data():
    try:
        # Extract the Google access token from HttpOnly cookie
        google_access_token = request.cookies.get('access_token_cookie')
        current_app.logger.info(f"Received Google access token from cookie: {google_access_token}")
        if not google_access_token:
            current_app.logger.warning("Access token cookie is missing")
            return jsonify({'message': 'Access token is missing'}), 401

        return GoogleAuth.retrieve_data(google_access_token)

    except Exception as e:
        current_app.logger.error(f"Error in google_user_data endpoint: {e}")
        return jsonify({'message': 'Internal server error'}), 500


# Purges all of the cookies in case they logged in normally before
@login_routes_bp.route('/logout', methods=['POST'])
def logout():
    return GoogleAuth.logout()