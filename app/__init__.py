import os
from flask import Flask, jsonify, session, request
from flask_session import Session
from flask_cors import CORS
from pymongo import MongoClient
import dotenv
from flask_jwt_extended import JWTManager
import logging
from datetime import timedelta
from flask_limiter import Limiter, RateLimitExceeded
from flask_limiter.util import get_remote_address
from datetime import datetime
from redis import Redis

dotenv_path = "D:\\Projects\\Python\\math-quiz\\app\\important_variables.env"
dotenv.load_dotenv(dotenv_path)
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
jwt = JWTManager(app)
app.config['JWT_COOKIE_CSRF_PROTECT'] = True
app.secret_key = os.getenv('FLASK_SECRET_KEY')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')

app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(seconds=int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600)))
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(seconds=int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 604800)))

app.config['JWT_TOKEN_LOCATION'] = ["cookies"]
app.config['JWT_HEADER_NAME'] = 'Authorization'
app.config['JWT_HEADER_TYPE'] = 'Bearer'

Session(app)

if not app.secret_key:
    raise ValueError("No secret key set for Flask application")
if not app.config['JWT_SECRET_KEY']:
    raise ValueError("No JWT secret key set")
if not app.config['JWT_ACCESS_TOKEN_EXPIRES']:
    raise ValueError("No JWT access token expiration time set")

CORS(app, resources={r"/*": {"origins": "https://localhost:8080"}}, supports_credentials=True)
client = MongoClient("mongodb+srv://wombat:Glc4GncM@womcluster.vdiu8vi.mongodb.net/")
db = client.get_database('mathQuizDatabase')
rate_limiting = db.get_collection('rate_limiting')

redis_client = Redis(host='localhost', port=6379, db=0)

def exclude_options():
    # Exclude OPTIONS requests from rate limiting
    if request.method == 'OPTIONS':
        return 'exclude'
    return get_remote_address()

limiter = Limiter(
    app=app,
    key_func=exclude_options,
    storage_uri="redis://localhost:6379",
    default_limits_exempt_when=lambda: False
)

from app.routes import main_route, account_routes, login_routes, data_routes, pdf_routes, util_routes

app.register_blueprint(main_route.bp)
app.register_blueprint(account_routes.account_routes_bp)
app.register_blueprint(login_routes.login_routes_bp)
app.register_blueprint(data_routes.data_routes_bp)
app.register_blueprint(pdf_routes.pdf_routes_bp)
app.register_blueprint(util_routes.util_routes_bp)