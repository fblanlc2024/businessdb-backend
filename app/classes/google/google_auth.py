from flask import Flask, Blueprint, redirect, request, jsonify, make_response, current_app
import requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from google.auth.transport import requests as google_requests
import os
from app import db
from datetime import datetime, timedelta
import logging
from google.auth.transport import requests as google_auth_requests
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token
from google.auth.exceptions import RefreshError
import json
import calendar
from app import app, redis_client

CLIENT_ID = app.config['CLIENT_ID']
CLIENT_SECRET = app.config['CLIENT_SECRET']
REDIRECT_URI = app.config['REDIRECT_URI']
AUTH_URI = app.config['AUTH_URI']
TOKEN_URI = app.config['TOKEN_URI']
USER_INFO = app.config['USER_INFO']

class GoogleAuth:
    def __init__(self):
        pass
    
    def login():
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "auth_uri": AUTH_URI,
                    "token_uri": TOKEN_URI,
                    "redirect_uris": [REDIRECT_URI]
                }
            },
            scopes=["https://www.googleapis.com/auth/userinfo.profile"],
        )
        flow.redirect_uri = REDIRECT_URI
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes='true',
            prompt='select_account consent'
        )
        response = make_response(redirect(authorization_url))
        response.set_cookie('state', state, httponly=True)
        return response
 
    def callback(state):
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "auth_uri": AUTH_URI,
                    "token_uri": TOKEN_URI,
                    "redirect_uris": [REDIRECT_URI],
                }
            },
            scopes=["https://www.googleapis.com/auth/userinfo.profile"],
            state=state,
        )

        flow.redirect_uri = REDIRECT_URI
        authorization_response = request.url
        flow.fetch_token(authorization_response=authorization_response)

        credentials = flow.credentials
        session = google_requests.AuthorizedSession(credentials)
        user_info = session.get(USER_INFO).json()

        existing_account = db.google_accounts.find_one({"google_id": user_info['id']})

        if not existing_account:
            google_account = {
                "google_id": user_info['id'],
                "account_name": user_info['name'],
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_expiry": credentials.expiry,
                "isAdmin": False
            }
            db.google_accounts.insert_one(google_account)
        else:
            db.google_accounts.update_one(
                {"google_id": user_info['id']},
                {
                    "$set": {
                        "access_token": credentials.token,
                        "refresh_token": credentials.refresh_token,
                        "token_expiry": credentials.expiry
                    }
                }
            )

        response = make_response(redirect("https://localhost:8080/posting"))

        expiry_timestamp = credentials.expiry.timestamp()
        current_timestamp = datetime.utcnow().timestamp()
        seconds_until_expiry = expiry_timestamp - current_timestamp

        access_token_expiration = datetime.utcnow() + timedelta(seconds=seconds_until_expiry)
        response.set_cookie('access_token_cookie', credentials.token, expires=access_token_expiration, httponly=True, secure=True, samesite='None')
        response.set_cookie('id_token', credentials.id_token, expires=access_token_expiration, httponly=True, secure=True, samesite='None')

        refresh_token_expiration = GoogleAuth.add_months(datetime.utcnow(), 6)
        response.set_cookie('refresh_token_cookie', credentials.refresh_token, expires=refresh_token_expiration, httponly=True, secure=True, samesite='None')
        response.set_cookie('logged_in', 'true', httponly=False, max_age=5, secure=True, samesite='None')

        return response
    
    # Google OAuth tokens expire after 6 months of not logging in, but native refresh tokens are still good to keep in the database in case something happens to the Google tokens.
    def refresh_token(refresh_token):
        user_data = db.google_accounts.find_one({"refresh_token": refresh_token})
        if not user_data:
            return jsonify({'message': 'User not found'}), 401

        google_id = user_data['google_id']

        credentials = Credentials(
            None, refresh_token=refresh_token, token_uri=TOKEN_URI,
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET)

        request_client = google_auth_requests.Request()

        try:
            credentials.refresh(request_client)
        except RefreshError:
            response = make_response(jsonify({'message': 'Refresh token is invalid, please reauthenticate'}), 401)
            response.set_cookie('refresh_token_cookie', '', expires=0, httponly=True, secure=True, samesite='None')
            return response

        db.google_accounts.update_one(
            {"google_id": google_id},
            {"$set": {"access_token": credentials.token, "token_expiry": credentials.expiry}}
        )

        response = make_response(jsonify({'message': 'Token refreshed successfully'}))

        expiry_timestamp = credentials.expiry.timestamp()
        current_timestamp = datetime.utcnow().timestamp()
        seconds_until_expiry = expiry_timestamp - current_timestamp

        access_token_expiration = datetime.utcnow() + timedelta(seconds=seconds_until_expiry)

        response.set_cookie('access_token_cookie', credentials.token, expires=access_token_expiration, httponly=True, secure=True, samesite='None')

        return response

    # Retrieves data from MongoDB
    def retrieve_data(google_access_token):
        headers = {'Authorization': 'Bearer ' + google_access_token}
        response = requests.get(USER_INFO, headers=headers)

        if response.status_code != 200:
            current_app.logger.error("Invalid or expired Google access token")
            return jsonify({'message': 'Invalid or expired Google access token'}), 401

        google_user_info = response.json()
        google_user_id = google_user_info['id']

        current_app.logger.info(f"Successfully fetched Google user data for ID: {google_user_id}")

        user_data = db.google_accounts.find_one({"google_id": google_user_id})
        if not user_data:
            current_app.logger.warning(f"User not found for Google ID: {google_user_id}")
            return jsonify({'message': 'User not found'}), 404

        response_data = {
            'google_id': user_data["google_id"],
            'account_name': user_data["account_name"],
        }
        current_app.logger.info(f"Le response data: {response_data}")

        return jsonify(response_data), 200

    def logout():
        response = make_response(jsonify({'message': 'Logged out successfully'}))
        response.set_cookie('access_token', '', expires=0)
        response.set_cookie('access_token_cookie', '', expires=0)
        response.set_cookie('access_csrf_cookie', '', expires=0)
        response.set_cookie('refresh_token', '', expires=0)
        response.set_cookie('refresh_token_cookie', '', expires=0)
        response.set_cookie('refresh_csrf_cookie', '', expires=0)
        response.set_cookie('state', '', expires=0)
        response.set_cookie('id_token', '', expires=0)
        return response
    
    @staticmethod
    def add_months(source_date, months):
        month = source_date.month - 1 + months
        year = source_date.year + month // 12
        month = month % 12 + 1
        day = min(source_date.day, calendar.monthrange(year, month)[1])
        return datetime(year, month, day)