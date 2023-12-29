from datetime import datetime

class GoogleAccount:
    def __init__(self, google_id, account_name, isAdmin=False):
        self.google_id = google_id  # New field for Google ID
        self.account_name = account_name
        self.isAdmin = isAdmin
        self.created_at = datetime.datetime.utcnow()
        self.updated_at = datetime.datetime.utcnow()

    def to_dict(self):
        return {
            "google_id": self.google_id,  # Include Google ID in the dict
            "account_name": self.account_name,
            "is_admin": self.isAdmin,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def login(cls, google_auth, client_ip, redis_client):
        # Check rate limit
        rate_limit_response = google_auth.check_rate_limit(client_ip, redis_client)
        if rate_limit_response:
            return rate_limit_response

        # Generate Google authorization URL
        authorization_url, state = google_auth.generate_auth_url()
        return {
            'authorization_url': authorization_url,
            'state': state
        }
    
    def update_or_create_google_account(user_info, credentials, google_account_dal):
        existing_account = google_account_dal.find_google_account(google_id=user_info['id'])
        google_account_data = {
            "google_id": user_info['id'],
            "account_name": user_info['name'],
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_expiry": credentials.expiry,
        }

        if not existing_account:
            google_account_dal.create_google_account(google_account_data)
        else:
            google_account_dal.update_google_account("google_id", user_info['id'], credentials)

    @classmethod
    def refresh_user_access_token(cls, google_account_dal, refresh_token, credentials):
        user_data = google_account_dal.find_google_account(refresh_token=refresh_token)
        if not user_data:
            return None

        google_account_dal.update_google_account(
            "google_id", 
            user_data['google_id'], 
            {"access_token": credentials.token, "token_expiry": credentials.expiry}
        )
        return user_data
    
    def get_user_data(google_user_id, google_account_dal):
        user_data = google_account_dal.find_google_account(google_id=google_user_id)
        if user_data:
            return {
                'google_id': user_data["google_id"],
                'account_name': user_data["account_name"],
            }
        else:
            raise ValueError("User not found.........")