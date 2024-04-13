import os
import json
import logging
from io import BytesIO
from pymongo import MongoClient
import ibm_boto3
from ibm_botocore.client import Config
from dotenv import load_dotenv

current_script_dir = os.path.dirname(os.path.abspath(__file__))

project_root = os.path.dirname(current_script_dir)

dotenv_path = os.path.join(project_root, 'app', 'important_variables.env')
logging.info(f"Loading environment variables from: {dotenv_path}")

if not os.path.exists(dotenv_path):
    logging.error(f"Environment file not found at {dotenv_path}")

loaded = load_dotenv(dotenv_path)
if loaded:
    logging.info("Environment variables loaded successfully.")
else:
    logging.error("Failed to load environment variables.")

logging.basicConfig(level=logging.INFO)

# Automated script to loop through all of the collections in MongoDB and save them to JSON files via a BytesIO stream. Then uses IBM's cos SDK to write to an IBM Cloud Bucket.
# This file was containerized with Docker and uploaded to IBM as a containerized Kubernetes job.
def backup_database(db, bucket):
    try:
        for collection_name in db.list_collection_names():
            collection = db[collection_name]
            data = list(collection.find({}))
            data_json = json.dumps(data, default=str)
            data_bytes = data_json.encode('utf-8')
            data_stream = BytesIO(data_bytes)
            json_backup = f'{collection_name}_backup.json'
            bucket.upload_fileobj(Fileobj=data_stream, Key=json_backup)

        logging.info("Database backup success!")
        return True

    except Exception as e:
        logging.error(f"Database backup failed: {str(e)}")
        return False

# Docker ran this main method.
def main():
    client = MongoClient(os.getenv('MONGODB_URI'))
    db = client.get_database('mathQuizDatabase')

    try:
        cos = ibm_boto3.resource('s3',
            ibm_api_key_id=os.getenv('IBM_API_KEY'),
            ibm_service_instance_id=os.getenv('IBM_SERVICE_INSTANCE_ID'),
            ibm_auth_endpoint=os.getenv('IBM_AUTH_URL'),
            config=Config(signature_version='oauth'),
            endpoint_url=os.getenv('IBM_ENDPOINT_URL')
        )

        logging.info(f"IBM_API_KEY: {os.getenv('IBM_API_KEY')}")
        logging.info(f"IBM_SERVICE_INSTANCE_ID: {os.getenv('IBM_SERVICE_INSTANCE_ID')}")
        logging.info(f"IBM_AUTH_URL: {os.getenv('IBM_AUTH_URL')}")
        logging.info(f"IBM_ENDPOINT_URL: {os.getenv('IBM_ENDPOINT_URL')}")
        fbla_bucket = cos.Bucket('fbla-bucket')
        logging.info("Connected to IBM Cloud Object Storage")
    except Exception as e:
        logging.error(f"Failed to connect to IBM Cloud Object Storage: {str(e)}")
        return

    backup_database(db, fbla_bucket)

if __name__ == "__main__":
    main()