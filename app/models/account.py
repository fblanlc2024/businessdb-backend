import datetime
class Account:
    def __init__(self, username, password_hash, isAdmin=False):
        self.username = username
        self.password_hash = password_hash
        self.isAdmin = isAdmin
        self.created_at = datetime.datetime.utcnow()
        self.updated_at = datetime.datetime.utcnow()

    def to_dict(self):
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "isAdmin": self.isAdmin,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }