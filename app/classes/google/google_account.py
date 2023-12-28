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


class GoogleAccount:
    def __init__(self, google_id, account_name, account_id, isAdmin=False):
        self.google_id = google_id  # New field for Google ID
        self.account_name = account_name
        self.account_id = account_id
        self.isAdmin = isAdmin
        self.created_at = datetime.datetime.utcnow()
        self.updated_at = datetime.datetime.utcnow()

    def to_dict(self):
        return {
            "google_id": self.google_id,  # Include Google ID in the dict
            "account_name": self.account_name,
            "account_id": self.account_id,
            "statistics": self.statistics,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    def login(self, client_ip):
        # Check rate limit
        rate_limit_response = self.google_auth.check_rate_limit(client_ip)
        if rate_limit_response:
            return rate_limit_response

        # Generate Google authorization URL
        authorization_url, state = self.google_auth.generate_auth_url()
        return {
            'authorization_url': authorization_url,
            'state': state
        }
    
    def update_or_create_google_account(self, user_info, credentials, google_account_dal):
        existing_account = google_account_dal.find_account({"google_id": user_info['id']})
        google_account_data = {
            "google_id": user_info['id'],
            "account_name": user_info['name'],
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_expiry": credentials.expiry,
        }

        if not existing_account:
            google_account_dal.create_account(google_account_data)
        else:
            google_account_dal.update_google_account("google_id", user_info['id'], credentials)

    def find_user_by_refresh_token(self, refresh_token, google_account_dal):
        return google_account_dal.find_account({"refresh_token": refresh_token})

    def update_access_token(self, user_id, access_token, token_expiry, google_account_dal):
        update_data = {"access_token": access_token, "token_expiry": token_expiry}
        google_account_dal.update_account({"account_id": user_id}, update_data)

    def refresh_user_access_token(self, refresh_token, credentials):
        user_data = self.find_user_by_refresh_token(refresh_token)
        if not user_data:
            return None

        self.update_access_token(user_data['account_id'], credentials.token, credentials.expiry)
        return user_data
    
    def get_user_data(self, google_user_id, google_accounts_dal):
        user_data = google_accounts_dal.find_one({"google_id": google_user_id})
        if user_data:
            return {
                'google_id': user_data["google_id"],
                'account_name': user_data["account_name"],
                'account_id': user_data["account_id"]
            }
        else:
            raise ValueError("User not found")