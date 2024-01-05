from flask import jsonify, current_app
import requests
from app import db
import re
from ...models.business import Business
from ...routes.util_routes import is_user_admin
from ...models.address import Address
from ...models.linker import Linker
from app import app

businesses_collection = db.businesses
counters_collection = db.counters
accounts_collection = db.accounts
google_accounts_collection = db.google_accounts
addresses_collection = db.addresses
linker_collection = db.linker

FOURSQUARE_API_KEY = app.config['FOURSQUARE_API_KEY']

class DataHandler:
    def __init__(self):
        pass

    def get_businesses():
        businesses = businesses_collection.find({}, {'_id': 0, 'business_id': 1, 'business_name': 1})
        business_list = list(businesses)

        return jsonify(business_list)

    def get_business_info(business_name, is_admin):
        # Fields to project for all users
        business_info_fields = {
            "business_id": "$business_id",
            "business_name": "$business_name",
            "organization_type": "$organization_type",
            "resources_available": "$resources_available",
            "has_available_resources": "$has_available_resources",
            "contact_info": "$contact_info"
        }

        # Additional fields for admin users
        if is_admin:
            business_info_fields.update({
                "yearly_revenue": "$yearly_revenue",
                "employee_count": "$employee_count",
                "customer_satisfaction": "$customer_satisfaction",
                "website_traffic": "$website_traffic"
            })

        pipeline = [
            {"$match": {"business_name": business_name}},
            {"$lookup": {
                "from": linker_collection.name,
                "localField": "business_id",
                "foreignField": "business_id",
                "as": "linker_info"
            }},
            {"$unwind": {
                "path": "$linker_info",
                "preserveNullAndEmptyArrays": True
            }},
            {"$lookup": {
                "from": addresses_collection.name,
                "localField": "linker_info.address_id",
                "foreignField": "address_id",
                "as": "address_info"
            }},
            {"$unwind": {
                "path": "$address_info",
                "preserveNullAndEmptyArrays": True
            }},
            {"$project": {
                "business_info": business_info_fields,
                "address_info": "$address_info",
                "_id": 0
            }}
        ]

        result = list(businesses_collection.aggregate(pipeline))

        if not result:
            return jsonify({'error': 'Business not found'}), 404

        # Convert ObjectId to string in the address_info
        for doc in result:
            if 'address_info' in doc and '_id' in doc['address_info']:
                doc['address_info']['_id'] = str(doc['address_info']['_id'])

        output = {
            "business_info": result[0]['business_info'] if result[0].get('business_info') else {},
            "addresses": [doc['address_info'] for doc in result if 'address_info' in doc]
        }

        return jsonify(output)
    
    def add_business(business_data):
        print("Received business data:", business_data)
        required_fields = ['business_name', 'organization_type', 'resources_available', 'has_available_resources', 'contact_info']

        # Validate required fields
        for field in required_fields:
            if field not in business_data or (isinstance(business_data[field], str) and not business_data[field].strip()):
                return jsonify({'error': f'Missing or empty required field: {field}'}), 400
            if field == 'has_available_resources' and not isinstance(business_data[field], bool):
                return jsonify({'error': f'Invalid data type for field: {field}'}), 400

        # Validate address fields
        address_fields = ['line1', 'city', 'state', 'zipcode', 'country']
        if 'address' not in business_data or not isinstance(business_data['address'], dict):
            return jsonify({'error': 'Missing or invalid address field'}), 400
        for address_field in address_fields:
            if address_field not in business_data['address'] or not business_data['address'][address_field].strip():
                return jsonify({'error': f'Missing or empty address field: {address_field}'}), 400

        # Validate zipcode format
        if not re.match(r'^\d{5}$', business_data['address']['zipcode']):
            return jsonify({'error': 'Invalid zipcode format.'}), 400

        try:
            # Create Address instance and add address
            address = Address()
            address_id = DataHandler.get_next_address_id()
            address.add_address(
                address_id,
                business_data['address']['line1'],
                business_data['address'].get('line2', ''),
                business_data['address']['city'],
                business_data['address']['state'],
                business_data['address']['zipcode'],
                business_data['address']['country']
            )

            # Insert address data into addresses_collection
            addresses_collection.insert_one(address.to_dict())

            # Create new business without the address
            new_business = Business(
                business_name=business_data['business_name'],
                organization_type=business_data['organization_type'],
                resources_available=business_data['resources_available'],
                has_available_resources=business_data['has_available_resources'],
                contact_info=business_data['contact_info']
            )
            new_business.business_id = DataHandler.get_next_business_id()

            # Insert the new business
            insert_result = businesses_collection.insert_one(new_business.to_dict())
            inserted_id = insert_result.inserted_id

            linker = Linker()
            linker.add_link(new_business.business_id, address_id)

            # Insert link data into linker_collection
            linker_collection.insert_one(linker.to_dict())

            # Retrieve the inserted business data
            inserted_business = businesses_collection.find_one({'_id': inserted_id})
            if inserted_business:
                inserted_business['_id'] = str(inserted_business['_id'])  # Convert ObjectId to string
                return jsonify(inserted_business), 201
            else:
                return jsonify({'error': 'Failed to retrieve the added business'}), 500

        except KeyError as e:
            return jsonify({'error': f'Missing address component: {e}'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        
    def autocomplete(query):
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
    
    
    def edit_business_info(business_id, business_info):
        current_app.logger.info(f"request data for edit: {business_info}")
        
        # Validate integers for yearly_revenue, employee_count, and website_traffic
        for field in ['yearly_revenue', 'employee_count', 'website_traffic']:
            if field in business_info and not isinstance(business_info[field], int):
                return jsonify({"error": f"{field} must be an integer"}), 400

        # Validate float or int for customer_satisfaction
        if 'customer_satisfaction' in business_info:
            if not isinstance(business_info['customer_satisfaction'], (int, float)):
                return jsonify({"error": "Customer satisfaction must be a number (integer or float)"}), 400

        try:
            result = businesses_collection.update_one(
                {"business_id": business_id},
                {"$set": business_info}
            )
            if result.matched_count == 0:
                return jsonify({"error": "Business not found"}), 404
            elif result.modified_count == 0:
                return jsonify({"error": "No changes were made"}), 200

            return jsonify({"message": "Business information updated successfully"}), 200
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        except Exception as e:
            return jsonify({"error": "An error occurred"}), 500
        
    def delete_business_by_id(business_id):
        pipeline = [
            {"$match": {"business_id": business_id}},
            {"$lookup": {
                "from": "linker",
                "localField": "business_id",
                "foreignField": "business_id",
                "as": "linked_addresses"
            }},
            {"$unwind": "$linked_addresses"},
            {"$lookup": {
                "from": "addresses",
                "localField": "linked_addresses.address_id",
                "foreignField": "address_id",
                "as": "address_details"
            }},
            {"$unwind": "$address_details"},
            {"$project": {"address_id": "$address_details.address_id"}}
        ]

        # Get all linked address IDs
        linked_address_ids = [
            doc['address_id'] for doc in businesses_collection.aggregate(pipeline)
        ]

        # Delete all linked addresses
        if linked_address_ids:
            addresses_collection.delete_many({"address_id": {"$in": linked_address_ids}})

        # Delete the business document
        business_delete_result = businesses_collection.delete_one({"business_id": business_id})
        if business_delete_result.deleted_count == 0:
            return jsonify({"error": "Business not found or already deleted"}), 404

        # Delete all link documents
        linker_collection.delete_many({"business_id": business_id})

        return jsonify({"message": "Business and all associated addresses deleted successfully"}), 200

    def add_business_address(business_id, address_data):
        address = Address()
        address_id = DataHandler.get_next_address_id()
        address.add_address(
            address_id,
            address_data['line1'],
            address_data.get('line2', ''),
            address_data['city'],
            address_data['state'],
            address_data['country'],
            address_data['zipcode'],
            address_data['country']
        )

        addresses_collection.insert_one(address.to_dict())
        
        linker = Linker()
        linker.add_linker(business_id, address_id)
        linker_collection.insert_one(linker.to_dict())

    @staticmethod
    def get_next_business_id():
        result = counters_collection.find_one_and_update(
            {'_id': 'business_id'},
            {'$inc': {'seq': 1}},
            return_document=True
        )
        return result['seq']
    
    @staticmethod
    def get_next_address_id():
        result = counters_collection.find_one_and_update(
            {'_id': 'address_id'},
            {'$inc': {'seq': 1}},
            return_document=True
        )
        return result['seq']