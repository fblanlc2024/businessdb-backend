from flask import Blueprint, redirect, request, jsonify, make_response, current_app
from app import db
from datetime import datetime, timedelta
import calendar
import logging

from ..classes.google.google_account import GoogleAccount
from ..classes.google.google_auth import GoogleAuth
from ..classes.google.google_account_dal import GoogleAccountDAL

from app import redis_client

login_routes_bp = Blueprint('login_routes_bp', __name__)

google_account_dal = GoogleAccountDAL(db)
google_auth = GoogleAuth(google_account_dal)

@login_routes_bp.route("/login")
def login_route():
    client_ip = request.remote_addr
    login_result = GoogleAccount.login(
        google_auth,
        client_ip,
        redis_client=redis_client
    )

    return create_login_response(login_result)

@login_routes_bp.route("/login/callback")
def callback_route():
    state = request.cookies.get('state')
    authorization_response = request.url
    credentials = google_auth.complete_oauth_flow(authorization_response, state)
    user_info = google_auth.get_user_info(credentials)
    current_app.logger.info(f"user_info from login callback (the target issue): {user_info}")
    GoogleAccount.update_or_create_google_account(user_info, credentials, google_account_dal)

    return create_callback_response(credentials, 'https://localhost:8080/posting')

@login_routes_bp.route('/google_token_refresh', methods=['POST'])
def google_token_refresh():
    refresh_token = request.cookies.get('refresh_token')
    if not refresh_token:
        return jsonify({'message': 'Refresh token not found'}), 401

    credentials = google_auth.handle_token_refresh(refresh_token)
    if not credentials:
        return jsonify({'message': 'Invalid credentials'}), 500
    if not credentials:
        response = clear_refresh_token_cookie()
        return response
    
    user_data = GoogleAccount.refresh_user_access_token(google_account_dal, refresh_token, credentials)
    if not user_data:
        return jsonify({'message': 'User not found'}), 401

    response = create_refresh_token_response(credentials)
    return response

@login_routes_bp.route('/google_user_data')
def google_user_data():
    try:
        current_app.logger.debug("Entering /google_user_data route")
        google_access_token = request.cookies.get('access_token')
        current_app.logger.debug(f"Google access token: {google_access_token}")

        if not google_access_token:
            current_app.logger.warning("Access token is missing")
            return jsonify({'message': 'Access token is missing'}), 401

        user_info = google_auth.fetch_user_info_from_google(google_access_token)
        current_app.logger.debug(f"User info retrieved: {user_info}")
        google_user_id = user_info['id']
        current_app.logger.debug(f"Google User ID: {google_user_id}")

        user_data = GoogleAccount.get_user_data(google_user_id, google_account_dal)
        current_app.logger.debug(f"User data: {user_data}")

        return jsonify(user_data), 200
    
    except ValueError as e:
        current_app.logger.error(f"ValueError in /google_user_data: {e}")
        return jsonify({'message': str(e)}), 401
    
    except Exception as e:
        current_app.logger.error(f"Exception in /google_user_data: {e}")
        return jsonify({'message': 'Internal server error'}), 500

@login_routes_bp.route('/logout', methods=['POST'])
def logout():
    return google_auth.logout_user()

# Helper methods start here
def add_months(source_date, months):
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day)

def create_login_response(login_result):
    if 'error' in login_result:
        return jsonify(login_result), 429

    authorization_url = login_result['authorization_url']
    state = login_result['state']
    response = make_response(redirect(authorization_url))
    response.set_cookie('state', state, httponly=True)
    return response

def create_callback_response(credentials, redirect_url):
    response = make_response(redirect(redirect_url))

    # Set access token in HttpOnly cookie
    access_token_expiration = datetime.utcnow() + timedelta(seconds=(credentials.expiry.timestamp() - datetime.utcnow().timestamp()))
    response.set_cookie('access_token', credentials.token, expires=access_token_expiration, httponly=True, secure=True, samesite='None')

    # Set refresh token in HttpOnly cookie
    refresh_token_expiration = add_months(datetime.utcnow(), 6)
    response.set_cookie('refresh_token', credentials.refresh_token, expires=refresh_token_expiration, httponly=True, secure=True, samesite='None')
    
    return response

def clear_refresh_token_cookie():
    response = make_response(jsonify({'message': 'Refresh token is invalid, please reauthenticate'}), 401)
    response.set_cookie('refresh_token', '', expires=0, httponly=True, secure=True, samesite='None')
    return response

def create_refresh_token_response(credentials):
    try:
        # Calculate the expiration time for the new access token
        expiry_timestamp = credentials.expiry.timestamp()
        current_timestamp = datetime.utcnow().timestamp()
        seconds_until_expiry = expiry_timestamp - current_timestamp
        access_token_expiration = datetime.utcnow() + timedelta(seconds=seconds_until_expiry)

        # Prepare the response
        response = jsonify({'message': 'Token refreshed successfully'})
        response = make_response(response)

        # Set the new access token in an HttpOnly cookie
        response.set_cookie('access_token', value=credentials.token, expires=access_token_expiration, httponly=True, secure=True, samesite='None')
        return response
    
    except Exception as e:
        return jsonify({'message': str(e)}), 500