from flask import jsonify, make_response, current_app
import requests
from google_auth_oauthlib.flow import Flow
from google.auth.transport import requests as google_requests
from google.auth.transport import requests as google_auth_requests
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from app import app

CLIENT_ID = app.config['CLIENT_ID']
CLIENT_SECRET = app.config['CLIENT_SECRET']
REDIRECT_URI = app.config['REDIRECT_URI']
AUTH_URI = app.config['AUTH_URI']
TOKEN_URI = app.config['TOKEN_URI']
USER_INFO = app.config['USER_INFO']

class GoogleAuth:
    def __init__(self, google_account_dal):
        self.google_account_dal = google_account_dal

    def check_rate_limit(self, client_ip, redis_client):
        ip_rate_limit_key = f"ip_rate_limit:{client_ip}"
        if redis_client.exists(ip_rate_limit_key):
            # If the key exists, it means the rate limit has been exceeded
            return {'error': 'IP rate limit exceeded. Please try again later.'}, 429
        return None

    def generate_auth_url(self):
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
        print(f"Refreshed credentials: {credentials}")  # Log the refreshed credentials
        return credentials

    def handle_token_refresh(self, refresh_token):
        try:
            credentials = self.refresh_google_token(refresh_token)
            return credentials
        except RefreshError as e:
            print(f"Failed to refresh token: {e}")  # Log the specific refresh error
            return None
        
    def fetch_user_info_from_google(self, access_token):
        try:
            current_app.logger.debug(f"Fetching user info from Google with token: {access_token}")
            headers = {'Authorization': f'Bearer {access_token}'}
            response = requests.get(USER_INFO, headers=headers)
            current_app.logger.debug(f"Google response status: {response.status_code}")

            if response.status_code == 200:
                user_info = response.json()
                current_app.logger.debug(f"User info response: {user_info}")
                return user_info
            else:
                current_app.logger.warning("Invalid or expired Google access token")
                raise ValueError("Invalid or expired Google access token")

        except Exception as e:
            current_app.logger.error(f"Error fetching user info: {e}")
            raise

        
    def logout_user(self):
        response = make_response(jsonify({'message': 'Logged out successfully'}))
        cookies_to_clear = [
            'access_token', 'access_token_cookie', 'refresh_token',
            'refresh_token_cookie', 'state', 'id_token', 'logged_in'
        ]
        for cookie in cookies_to_clear:
            response.set_cookie(cookie, '', expires=0)
        return response