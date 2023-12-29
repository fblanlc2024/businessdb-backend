class GoogleAccountDAL:
    def __init__(self, db):
        self.google_accounts_collection = db.google_accounts
        self.refresh_tokens_collection = db.refresh_tokens
    
    def find_google_account(self, google_id=None, refresh_token=None):
        if google_id:
            # Find account by Google ID
            return self.google_accounts_collection.find_one({"google_id": google_id})
        elif refresh_token:
            # Find account by refresh token
            return self.google_accounts_collection.find_one({"refresh_token": refresh_token})
        else:
            return None

    def create_google_account(self, google_account):
        return self.google_accounts_collection.insert_one(google_account)
    
    def update_google_account(self, id_key, id_value, credentials):
        update_data = {
            "access_token": credentials.token,
            "token_expiry": credentials.expiry
        }

        # Include refresh_token in the update only if it exists
        if hasattr(credentials, 'refresh_token') and credentials.refresh_token:
            update_data["refresh_token"] = credentials.refresh_token
        
        filter_query = {id_key: id_value}

        # Perform the update
        return self.google_accounts_collection.update_one(filter_query, {"$set": update_data})
    
    