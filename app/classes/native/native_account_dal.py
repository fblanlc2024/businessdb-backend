from datetime import datetime
from datetime import timedelta

class NativeAccountDAL:
    def __init__(self, db):
        self.accounts_collection = db.accounts
        self.google_accounts_collection = db.google_accounts
        self.refresh_tokens_collection = db.refresh_tokens

    def find_account(self, username):
        return self.accounts_collection.find_one({'username': username})

    def create_account(self, account):
        return self.accounts_collection.insert_one(account.to_dict())
    
    def update_account(self, username, updates):
        return self.accounts_collection.update_one({'username': username}, {'$set': updates})
        
    def delete_account(self, username):
        return self.accounts_collection.delete_one({'username': username})
    
    def update_password(self, username, new_password):
        return self.accounts_collection.update_one({'username': username}, {'$set': {'password_hash': new_password}})
    
    def find_refresh_token(self, username=None, refresh_token=None):
        if refresh_token:
            return self.refresh_tokens_collection.find_one({"token": refresh_token})
        elif username:
            return self.refresh_tokens_collection.find_one({"userId": username})
        else:
            return None
    
    def replace_refresh_token(self, old_refresh_token, new_refresh_token, current_user):
            return self.refresh_tokens_collection.find_one_and_replace(
                {"token": old_refresh_token},
                {"token": new_refresh_token, "userId": current_user, "expiresAt": datetime.utcnow() + timedelta(days=30)}
            )
    
    def insert_refresh_token(self, refresh_token, username):
        return self.refresh_tokens_collection.insert_one({
            "token": refresh_token,
            "userId": username,
            "expiresAt": datetime.utcnow() + timedelta(days=30)
        })
    
    def is_google_account(self, username):
        return self.google_accounts_collection.find_one({'account_name': username}) is not None