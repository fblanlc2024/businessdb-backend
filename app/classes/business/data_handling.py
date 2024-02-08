from flask import jsonify, current_app
import requests
from app import db, cos
import re
import json
from io import BytesIO
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

fbla_bucket = cos.Bucket('fbla-bucket')

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
    
    def add_business(business_data):
        current_app.logger.info(f"received data in refactored add_business method: {business_data}")
        validation_result = DataHandler.validate_data(business_data)
        if validation_result is not True:
            current_app.logger.info(f"the validation result is: {validation_result}")
            return validation_result
        
        current_app.logger.info(f"the validation result is: {validation_result}")
        try:
            return DataHandler.add_business_data(business_data)
        except KeyError as e:
            return jsonify({'error': f'Missing address component: {e}'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        
    def add_multiple_businesses(businesses_data):
        valid_businesses = []
        addresses = []
        business_docs = []
        linker_docs = []

        for business_data in businesses_data:
            if DataHandler.validate_data(business_data):
                addresses.append(business_data['address'])
                valid_businesses.append(business_data)
            else:
                continue

        address_insertion_results = addresses_collection.insert_many(addresses)
        address_ids = address_insertion_results.inserted_ids

        for i, business_data in enumerate(valid_businesses):
            new_business_doc = {
                "business_name": business_data['business_name'],
                "organization_type": business_data['organization_type'],
                "resources_available": business_data['resources_available'],
                "has_available_resources": business_data['has_available_resources'],
                "contact_info": business_data['contact_info'],
                "yearly_revenue": business_data['yearly_revenue'],
                "employee_count": business_data['employee_count'],
                "customer_satisfaction": business_data['customer_satisfaction'],
                "website_traffic": business_data['website_traffic'],
            }
            business_docs.append(new_business_doc)

        business_insertion_results = businesses_collection.insert_many(business_docs)
        business_ids = business_insertion_results.inserted_ids

        for i, business_id in enumerate(business_ids):
            linker_doc = {
                "business_id": business_id,
                "address_id": address_ids[i]
            }
            linker_docs.append(linker_doc)

        linker_collection.insert_many(linker_docs)

        return jsonify({"message": f"Successfully added {len(business_docs)} businesses"}), 201
        
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
        
    def delete_business_address(address_id):
        # Delete the address document
        address_delete_result = addresses_collection.delete_one({"address_id": address_id})
        if address_delete_result.deleted_count == 0:
            return jsonify({"error": "Address not found or already deleted"}), 404

        # Delete the link document in the linker collection
        linker_delete_result = linker_collection.delete_one({"address_id": address_id})
        if linker_delete_result.deleted_count == 0:
            return jsonify({"message": "Address deleted successfully, but no linked record found"}), 200

        return jsonify({"message": "Address and its link deleted successfully"}), 200

    def add_business_address(business_id, address_data):
        address = Address()
        address_id = DataHandler.get_next_address_id()

        address_fields = ['line1', 'city', 'state', 'zipcode', 'country']
        if not address_data or not isinstance(address_data, dict):
            return jsonify({'error': 'Missing or invalid address field'}), 400
        for address_field in address_fields:
            if address_field not in address_data or not address_data[address_field].strip():
                return jsonify({'error': f'Missing or empty address field: {address_field}'}), 400

        # Validate zipcode format
        if not re.match(r'^\d{5}$', address_data['zipcode']):
            return jsonify({'error': 'Invalid zipcode format.'}), 400
        
        address.add_address(
            address_id=address_id,
            address_line_1=address_data['line1'],
            address_line_2=address_data.get('line2', ''),
            city=address_data['city'],
            state=address_data['state'],
            zipcode=address_data['zipcode'],
            country=address_data['country']
        )

        addresses_collection.insert_one(address.to_dict())
        
        linker = Linker()
        linker.add_link(business_id, address_id)
        linker_collection.insert_one(linker.to_dict())

        return jsonify({"message": "Address added successfully"}), 200
    
    def edit_business_address(address_id, address_data):
        try:
            field_mapping = {
                'line1': 'address_line_1',
                'line2': 'address_line_2',  # Assuming you have a similar case for line2
                'city': 'city',
                'state': 'state',
                'zipcode': 'zipcode',
                'country': 'country'
            }

            if not address_data or not isinstance(address_data, dict):
                return jsonify({'error': 'Missing or invalid address field'}), 400

            update_data = {}
            for input_field, db_field in field_mapping.items():
                if input_field in address_data and address_data[input_field].strip():
                    update_data[db_field] = address_data[input_field]
                elif db_field != 'address_line_2':  # Skip optional field
                    return jsonify({'error': f'Missing or empty required field: {input_field}'}), 400

            # Validate zipcode format
            if 'zipcode' in update_data and not re.match(r'^\d{5}$', update_data['zipcode']):
                return jsonify({'error': 'Invalid zipcode format.'}), 400

            # Update the address in the database
            update_result = addresses_collection.update_one(
                {'address_id': address_id},
                {'$set': update_data}
            )

            if update_result.matched_count == 0:
                return jsonify({'error': 'Address not found'}), 404
            elif update_result.modified_count == 0:
                return jsonify({'error': 'No changes were made'}), 200

            return jsonify({'message': 'Address updated successfully'}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        
    
    def backup_database():
        try:
            # Iterate over all collections in the database
            for collection_name in db.list_collection_names():
                # Access each collection
                collection = db[collection_name]
                data = list(collection.find({}))

                # Serialize the data of each collection
                data_json = json.dumps(data, default=str)
                data_bytes = data_json.encode('utf-8')
                data_stream = BytesIO(data_bytes)

                # Create a unique backup file name for each collection
                json_backup = f'{collection_name}_backup.json'

                # Upload each collection's data to the bucket
                fbla_bucket.upload_fileobj(Fileobj=data_stream, Key=json_backup)

            return jsonify({"message": "Database backup success!"}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 400
        
    @staticmethod
    def validate_data(business_data):
        current_app.logger.info(f"Received business data in validate_data method: {business_data}")
        required_fields = ['business_name', 'organization_type', 'resources_available', 
                        'has_available_resources', 'contact_info', 'yearly_revenue', 
                        'employee_count', 'customer_satisfaction', 'website_traffic']

        # Validate required fields
        for field in required_fields:
            if field not in business_data or (isinstance(business_data[field], str) and not business_data[field].strip()):
                return jsonify({'error': f'Missing or empty required field: {field}'}), 400
            if field == 'has_available_resources' and not isinstance(business_data[field], bool):
                return jsonify({'error': f'Invalid data type for field: {field}'}), 400
            if field in ['yearly_revenue', 'employee_count', 'website_traffic'] and not isinstance(business_data[field], int):
                return jsonify({'error': f'Invalid data type for field: {field}. Expected integer.'}), 400
            if field == 'customer_satisfaction' and not isinstance(business_data[field], (float, int)):
                return jsonify({'error': f'Invalid data type for field: {field}. Expected float or integer.'}), 400
            
        contact_info = business_data.get('contact_info', '')
        phone_number_pattern = r'^\d{10,11}$'
        if not re.match(phone_number_pattern, contact_info):
            return jsonify({'error': 'Invalid phone number format. Expected 10 or 11 digits.'}), 400
        
        if isinstance(business_data.get('has_available_resources'), str):
            if business_data['has_available_resources'].lower() == 'true':
                business_data['has_available_resources'] = True
            elif business_data['has_available_resources'].lower() == 'false':
                business_data['has_available_resources'] = False

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
        
        return True
        
    @staticmethod
    def add_business_data(business_data):
        # Create Address instance and add address
        address = Address()
        address_id = DataHandler.get_next_address_id()
        address.add_address(
            address_id=address_id,
            address_line_1=business_data['address']['line1'],
            address_line_2=business_data['address'].get('line2', ''),
            city=business_data['address']['city'],
            state=business_data['address']['state'],
            zipcode=business_data['address']['zipcode'],
            country=business_data['address']['country']
        )

        # Insert address data into addresses_collection
        addresses_collection.insert_one(address.to_dict())

        # Create new business without the address
        new_business = Business(
            business_name=business_data['business_name'],
            organization_type=business_data['organization_type'],
            resources_available=business_data['resources_available'],
            has_available_resources=business_data['has_available_resources'],
            contact_info=business_data['contact_info'],
            yearly_revenue=business_data['yearly_revenue'],
            employee_count=business_data['employee_count'],
            customer_satisfaction=business_data['customer_satisfaction'],
            website_traffic=business_data['website_traffic']
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