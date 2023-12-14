from flask import Blueprint, jsonify, request, current_app, redirect, url_for, make_response, render_template
import pymongo
import requests
from pymongo import MongoClient
from pymongo.errors import WriteError
import bcrypt
from flask_jwt_extended import (jwt_required, create_access_token, 
                                create_refresh_token, get_jwt_identity, 
                                get_jwt, verify_jwt_in_request, get_csrf_token)
from flask_jwt_extended.exceptions import JWTExtendedException
import logging
import datetime
import jwt
from flask_limiter import RateLimitExceeded

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from flask import Flask
from flask import jsonify
import re

from app import client, db
from app.models import Business
from .util_routes import is_user_admin
businesses_collection = db.businesses
counters_collection = db.counters
accounts_collection = db.accounts

FOURSQUARE_API_KEY = "fsq3ToBA7PvQLrce5qB5hgyRhLjn3L6D9JgVhgeAWKaCY0g="
data_routes_bp = Blueprint('data_routes', __name__)

@data_routes_bp.route('/api/businesses', methods=['GET'])
def get_businesses():
    businesses = businesses_collection.find({}, {'_id': 0, 'business_id': 1, 'business_name': 1})
    business_list = list(businesses)

    return jsonify(business_list)

@data_routes_bp.route('/api/business_info', methods=['GET'])
def get_business_info():
    business_name = request.args.get('name')

    # Query to find the document for the given business name
    business_info = businesses_collection.find_one(
        {"business_name": business_name},
        {"business_name": 0, "_id": 0}
    )

    if business_info:
        return jsonify(business_info)
    else:
        return jsonify({"error": "Business not found"}), 404


@data_routes_bp.route('/add_business', methods=['POST'])
def add_business():
    data = request.json
    print("Received business data:", data)
    required_fields = ['business_name', 'address', 'organization_type', 'resources_available', 'has_available_resources', 'contact_info']

    for field in required_fields:
        # Check if the field is not in data or if it's a string that's empty after stripping
        if field not in data or (isinstance(data[field], str) and not data[field].strip()):
            return jsonify({'error': f'Missing or empty required field: {field}'}), 400
        # Special case for boolean fields like 'has_available_resources'
        if field == 'has_available_resources' and not isinstance(data[field], bool):
            return jsonify({'error': f'Invalid data type for field: {field}'}), 400
        # Additional checks for 'address' fields
        if field == 'address':
            for address_field in ['number', 'street', 'city', 'state', 'zipcode', 'country']:
                if address_field not in data[field] or not data[field][address_field]:
                    return jsonify({'error': f'Missing or empty address field: {address_field}'}), 400

    # Additional format validations
    if 'zipcode' in data['address'] and not re.match(r'^\d{5}$', data['address']['zipcode']):
        return jsonify({'error': 'Invalid zipcode format.'}), 400

    if 'number' in data['address']:
        try:
            # Convert to integer and check if it raises an error
            int(data['address']['number'])
        except ValueError:
            return jsonify({'error': 'Address number must be an integer'}), 400

    try:
        new_business = Business(
            business_name=data['business_name'],
            address=data['address'],
            organization_type=data['organization_type'],
            resources_available=data['resources_available'],
            has_available_resources=data['has_available_resources'],
            contact_info=data['contact_info']
        )

        new_business.business_id = get_next_business_id()

        # Insert the new business and retrieve the inserted ID if possible
        insert_result = businesses_collection.insert_one(new_business.to_dict())
        inserted_id = insert_result.inserted_id

        # Retrieve the inserted business data
        inserted_business = businesses_collection.find_one({'_id': inserted_id})

        if inserted_business:
            # Convert the MongoDB document to a JSON-friendly format
            inserted_business['_id'] = str(inserted_business['_id'])  # Convert ObjectId to string

            return jsonify(inserted_business), 201
        else:
            return jsonify({'error': 'Failed to retrieve the added business'}), 500

    except KeyError as e:
        return jsonify({'error': f'Missing address component: {e}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@data_routes_bp.route('/delete_business/<int:business_id>', methods=['DELETE'])
def delete_business_by_id(business_id):
    try:
        result = businesses_collection.delete_one({'business_id': business_id})
        if result.deleted_count > 0:
            return jsonify({'message': 'Business deleted successfully'}), 200
        else:
            return jsonify({'error': 'Business not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@data_routes_bp.route('/autocomplete', methods=['GET'])
def autocomplete():
    query = request.args.get('query')
    url = "https://api.foursquare.com/v3/places/search"

    headers = {
        "Accept": "application/json",
        "Authorization": FOURSQUARE_API_KEY
    }

    params = {
        "query": query,
        "limit": 5  # Adjust limit as needed
    }

    response = requests.get(url, headers=headers, params=params)
    return jsonify(response.json())

def get_next_business_id():
    result = counters_collection.find_one_and_update(
        {'_id': 'business_id'},
        {'$inc': {'seq': 1}},
        return_document=True
    )
    return result['seq']


@data_routes_bp.route('/edit_business_info', methods=['POST'])
@jwt_required()
def edit_business_info():
    current_user = get_jwt_identity()

    try:
        if not is_user_admin(current_user, accounts_collection):
            return jsonify({"error": "Unauthorized access"}), 403

        data = request.json
        business_id = data['business_id']
        business_info = data['business_info']

        result = businesses_collection.update_one(
            {"business_id": business_id},
            {"$set": business_info}
        )
        if result.matched_count == 0:
            return jsonify({"error": "Business not found"}), 404
        elif result.modified_count == 0:
            return jsonify({"error": "No changes were made"}), 400

        return jsonify({"message": "Business information updated successfully"}), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": "An error occurred"}), 500