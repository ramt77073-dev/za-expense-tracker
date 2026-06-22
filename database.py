import os
from pymongo import MongoClient

MONGO_URL = os.getenv("MONGO_URL")

client = MongoClient(MONGO_URL)
db = client["expense_tracker"]

expenses_collection = db["expenses"]
users_collection = db["users"]