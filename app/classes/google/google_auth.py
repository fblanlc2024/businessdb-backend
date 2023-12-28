from flask import Flask, Blueprint, redirect, request, jsonify, make_response, current_app
import requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from google.auth.transport import requests as google_requests
import os
from app import db
from app.models import GoogleAccount
from datetime import datetime, timedelta
import logging
from google.auth.transport import requests as google_auth_requests
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token
from google.auth.exceptions import RefreshError
import json
import calendar
from app import redis_client

CLIENT_ID = current_app.config['CLIENT_ID']
CLIENT_SECRET = current_app.config['CLIENT_SECRET']
REDIRECT_URI = current_app.config['REDIRECT_URI']
AUTH_URI = current_app.config['AUTH_URI']
TOKEN_URI = current_app.config['TOKEN_URI']
USER_INFO = current_app.config['USER_INFO']

class GoogleAuth:
    def __init__(self, google_account_dal):
        self.google_account_dal = google_account_dal

    def check_rate_limit(self, client_ip):
        return self.google_account_dal.check_rate_limit(client_ip)

    def generate_auth_url(self, client_id, client_secret, redirect_uri, auth_uri, token_uri):
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": auth_uri,
                    "token_uri": token_uri,
                    "redirect_uris": [redirect_uri]
                }
            },
            scopes=["https://www.googleapis.com/auth/userinfo.profile"],
        )
        flow.redirect_uri = redirect_uri
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes='true',
            prompt='select_account consent'
        )
        return authorization_url, state
    
    def complete_oauth_flow(self, authorization_response, state):
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
        flow.fetch_token(authorization_response=authorization_response)
        return flow.credentials

    def get_user_info(self, credentials):
        session = google_requests.AuthorizedSession(credentials)
        return session.get(USER_INFO).json()
    
    def refresh_google_token(self, refresh_token):
        credentials = Credentials(
            None, refresh_token=refresh_token, token_uri=TOKEN_URI,
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET
        )

        request_client = google_auth_requests.Request()
        credentials.refresh(request_client)
        return credentials
    
    def handle_token_refresh(self, refresh_token):
        try:
            credentials = self.refresh_google_token(refresh_token)
            return credentials
        except RefreshError:
            return None
        
    def fetch_user_info_from_google(self, access_token):
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(USER_INFO, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise ValueError("Invalid or expired Google access token")
        
    def logout_user(self):
        response = make_response(jsonify({'message': 'Logged out successfully'}))
        cookies_to_clear = [
            'access_token', 'access_token_cookie', 'refresh_token',
            'refresh_token_cookie', 'state', 'id_token'
        ]
        for cookie in cookies_to_clear:
            response.set_cookie(cookie, '', expires=0)
        return response