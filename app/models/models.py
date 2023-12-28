import datetime

# For MongoDB/database model - native account has additional logic that should preferrably not be inside the database
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

# class GoogleAccount:
#     def __init__(self, google_id, account_name, account_id, isAdmin=False):
#         self.google_id = google_id  # New field for Google ID
#         self.account_name = account_name
#         self.account_id = account_id
#         self.isAdmin = isAdmin
#         self.created_at = datetime.datetime.utcnow()
#         self.updated_at = datetime.datetime.utcnow()

#     def to_dict(self):
#         return {
#             "google_id": self.google_id,  # Include Google ID in the dict
#             "account_name": self.account_name,
#             "account_id": self.account_id,
#             "statistics": self.statistics,
#             "created_at": self.created_at,
#             "updated_at": self.updated_at
#         }

class Business:
    def __init__(self, business_name, address, organization_type, resources_available, has_available_resources, contact_info):
        self.business_id = None
        self.business_name = business_name
        self.address = address
        self.organization_type = organization_type
        self.resources_available = resources_available
        self.has_available_resources = has_available_resources
        self.contact_info = contact_info

    def to_dict(self):
        return {
            "business_id": self.business_id,
            "business_name": self.business_name,
            "address": self.address,
            "organization_type": self.organization_type,
            "resources_available": self.resources_available,
            "has_available_resources": self.has_available_resources,
            "contact_info": self.contact_info,
        }