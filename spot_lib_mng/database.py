import datetime

import pymongo
from pymongo import MongoClient
from spot_lib_mng.config import settings

db = None
TOKEN_ID = 'token'

def get_db():
    global db
    if db:
        return db
    client = MongoClient(settings.mongodb_host, settings.mongodb_port)
    db = client[settings.db_name]
    return db


def insert_one(collection_name: str, query: dict) -> None:
    db[collection_name].insert_one(query)


def insert_many(collection_name: str, query: list) -> None:
    db[collection_name].insert_many(query)


def count_documents(collection_name: str, query: dict) -> int:
    return db[collection_name].count_documents(query)


def find_one(collection_name: str, query: dict) -> dict:
    return db[collection_name].find_one(query)


def find_many(collection_name: str, query: dict) -> list:
    cursor = db[collection_name].find(query)
    return cursor.to_list(None)


def remove_one(collection_name: str, query: dict) -> None:
    db[collection_name].remove_one(query)


def update_one(collection_name: str, query: dict, update: dict):
    collection = db[collection_name]
    update['modified_at'] = datetime.datetime.utcnow()
    update['modified_by'] = settings.modifier
    result = collection.update_one(query, {'$set': update}, upsert=True)
    if result.modified_count == 1:
        return True
    return False


def find_latest_documents(collection_name: str, amount: int):
    return list(db[collection_name].find().sort([('created_at', -1)]).limit(amount))


def get_stored_access_token():
    token_document = find_one(settings.token_collection_name, {'_id': TOKEN_ID})
    return token_document['token']


def store_access_token(token: str):
    if not get_stored_access_token():
        insert_one(settings.token_collection_name, {'_id': TOKEN_ID, 'token': token})
    else:
        update_one(settings.token_collection_name, {'_id': TOKEN_ID}, {'token': token})
