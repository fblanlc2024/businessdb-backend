import os
from flask import Flask, request
from flask_session import Session
from flask_cors import CORS
from pymongo import MongoClient
import dotenv
from flask_jwt_extended import JWTManager
import logging
from datetime import timedelta
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis
from flask_socketio import SocketIO
import ibm_boto3
from ibm_botocore.client import Config

current_dir = os.path.dirname(__file__)
dotenv_path = os.path.join(current_dir, 'important_variables.env')
dotenv.load_dotenv(dotenv_path)

logging.basicConfig(level=logging.DEBUG)

# Builds application and configures environmental variables.
app = Flask(__name__)
jwt = JWTManager(app)

app.secret_key = os.getenv('FLASK_SECRET_KEY')
app.config['JWT_COOKIE_CSRF_PROTECT'] = True
app.config["JWT_COOKIE_SECURE"] = True
app.config['JWT_CSRF_IN_COOKIES'] = True
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(seconds=int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600)))
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(seconds=int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 604800)))
app.config['JWT_TOKEN_LOCATION'] = ["cookies"]
app.config['JWT_HEADER_NAME'] = 'Authorization'
app.config['JWT_HEADER_TYPE'] = 'Bearer'
app.config['CLIENT_ID'] = os.getenv('CLIENT_ID')
app.config['CLIENT_SECRET'] = os.getenv('CLIENT_SECRET')
app.config['REDIRECT_URI'] = os.getenv('REDIRECT_URI')
app.config['AUTH_URI'] = os.getenv('AUTH_URI')
app.config['TOKEN_URI'] = os.getenv('TOKEN_URI')
app.config['USER_INFO'] = os.getenv('USER_INFO')
app.config['FOURSQUARE_API_KEY'] = os.getenv('FOURSQUARE_API_KEY')
#change
app.config['ATLAS_API_KEY'] = os.getenv('ATLAS_API_KEY')
app.config['ATLAS_GROUP_ID'] = os.getenv('ATLAS_GROUP_ID')
app.config['ATLAS_CLUSTER_NAME'] = os.getenv('ATLAS_CLUSTER_NAME')

app.config['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
app.config['IBM_API_KEY'] = os.getenv('IBM_API_KEY')
app.config['IBM_SERVICE_INSTANCE_ID'] = os.getenv('IBM_SERVICE_INSTANCE_ID')
app.config['IBM_AUTH_URL'] = os.getenv('IBM_AUTH_URL')
app.config['IBM_ENDPOINT_URL'] = os.getenv('IBM_ENDPOINT_URL')

#change
app.config['MONGODB_URI'] = os.getenv('MONGODB_URI')

app.config['ASSISTANT_ID'] = os.getenv('ASSISTANT_ID')
app.config['SENDING_EMAIL'] = os.getenv('SENDING_EMAIL')
app.config['SENDING_EMAIL_PASSWORD'] = os.getenv('SENDING_EMAIL_PASSWORD')
app.config['RECEIVING_EMAIL'] = os.getenv('RECEIVING_EMAIL')
app.config['ELEVENLABS_API_KEY'] = os.getenv('ELEVENLABS_API_KEY')
app.config['VOICE_ASSISTANT_PROMPT'] = os.getenv('VOICE_ASSISTANT_PROMPT')

Session(app)
socketio = SocketIO(app, cors_allowed_origins="*") 

if not app.secret_key:
    raise ValueError("No secret key set for Flask application")
if not app.config['JWT_SECRET_KEY']:
    raise ValueError("No JWT secret key set")
if not app.config['JWT_ACCESS_TOKEN_EXPIRES']:
    raise ValueError("No JWT access token expiration time set")


#This is the setup for mongoDb essentially
CORS(app, resources={r"/*": {"origins": ["https://localhost:8080", "https://fbla-project-23e7b.web.app"]}}, supports_credentials=True)
client = MongoClient(app.config['MONGODB_URI'])
db = client.get_database('businessdb')
rate_limiting = db.get_collection('rate_limiting')

redis_client = Redis(host='localhost', port=6379, db=0)

def exclude_options():
    if request.method == 'OPTIONS':
        return 'exclude'
    return get_remote_address()

limiter = Limiter(
    app=app,
    key_func=exclude_options,
    storage_uri="redis://localhost:6379",
    default_limits_exempt_when=lambda: False
)

try:
    cos = ibm_boto3.resource('s3',
        ibm_api_key_id=app.config['IBM_API_KEY'],
        ibm_service_instance_id=app.config['IBM_SERVICE_INSTANCE_ID'],
        ibm_auth_endpoint=app.config['IBM_AUTH_URL'],
        config=Config(signature_version='oauth'),
        endpoint_url=app.config['IBM_ENDPOINT_URL']
    )

    # Perform a simple operation to check the connection, like listing buckets
    buckets = list(cos.buckets.all())
    logging.info("Successfully connected to IBM Cloud Object Storage. Buckets available: {}".format([bucket.name for bucket in buckets]))

except Exception as e:
    logging.error("Failed to connect to IBM Cloud Object Storage: {}".format(e))

from app.routes import ai_socket_events, account_routes, login_routes, data_routes, pdf_routes, util_routes, ai_socket_events
app.register_blueprint(account_routes.account_routes_bp)
app.register_blueprint(login_routes.login_routes_bp)
app.register_blueprint(data_routes.data_routes_bp)
app.register_blueprint(pdf_routes.pdf_routes_bp)
app.register_blueprint(util_routes.util_routes_bp)
app.register_blueprint(ai_socket_events.ai_routes_bp)

from .routes.ai_socket_events import setup_socket_events
setup_socket_events(socketio)