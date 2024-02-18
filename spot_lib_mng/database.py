from datetime import datetime, timedelta
import json
import urllib.parse

from bson.json_util import dumps
from pymongo import MongoClient
from spot_lib_mng.config import settings
from pymongo.server_api import ServerApi

from spot_lib_mng.utils.requests import exec_get_request_with_headers_and_token_and_return_data
from spot_lib_mng.utils.utils import remove_metadata

db = None
TOKEN_ID = 'token'

DB_METADATA = {'_id': False, 'created_at': False, 'created_by': False, 'modified_at': False, 'modified_by': False}

imported_artist_ids = []
imported_track_ids = []


def get_db():
    global db
    if db:
        return db
    # client = MongoClient(settings.mongodb_host, settings.mongodb_port)
    uri = f"mongodb+srv://{urllib.parse.quote_plus(settings.mongodb_user)}:{urllib.parse.quote_plus(settings.mongodb_password)}@{settings.mongodb_host}?retryWrites=true&w=majority"
    client = MongoClient(uri, server_api=ServerApi('1'))
    db = client[settings.db_name]
    return db


def insert_one(collection_name: str, query: dict) -> None:
    db[collection_name].insert_one(query)


def insert_many(collection_name: str, query: list) -> None:
    db[collection_name].insert_many(query)


def count_documents(collection_name: str, query: dict) -> int:
    return db[collection_name].count_documents(query)


def find_one(collection_name: str, query: dict, exclude_metadata=False) -> dict:
    if exclude_metadata:
        return db[collection_name].find_one(query, DB_METADATA)
    return db[collection_name].find_one(query)


def find_many(collection_name: str, query: dict, select_dict=None, exclude_metadata=False) -> list:
    if select_dict:
        cursor = db[collection_name].find(query, select_dict)
    elif exclude_metadata:
        cursor = db[collection_name].find(query,
                                          DB_METADATA)
    else:
        cursor = db[collection_name].find(query)

    return list(cursor)


def remove_one(collection_name: str, query: dict) -> None:
    db[collection_name].remove_one(query)


def find_max(collection_name: str, attribute_name: str, limit: int):
    return db[collection_name].find({}, DB_METADATA).sort({attribute_name: -1}).limit(limit)


def update_one(collection_name: str, query: dict, update: dict):
    collection = db[collection_name]

    update['modified_at'] = datetime.utcnow()
    update['modified_by'] = settings.modifier
    created = {
        'created_at': datetime.utcnow(),
        'created_by': settings.modifier
    }

    result = collection.update_one(query, {'$set': update, '$setOnInsert': created}, upsert=True)
    if result.modified_count == 1:
        return True
    return False


def find_latest_documents(collection_name: str, amount: int):
    return list(db[collection_name].find().sort([('created_at', -1)]).limit(amount))


def get_access_token():
    return find_one(settings.token_collection_name, {'_id': TOKEN_ID})


#### app specific #####

def store_access_token(token: dict):
    token['_id'] = TOKEN_ID
    token['expiry_date'] = datetime.utcnow() + timedelta(0, token['expires_in'] - 5)
    if not get_access_token():
        insert_one(settings.token_collection_name, token)
    else:
        update_one(settings.token_collection_name, {'_id': TOKEN_ID}, token)


def get_latest_playlist_by_id(spotify_playlist_id: str):
    latest_playlists = json.loads(dumps(find_latest_documents(settings.playlist_collection_name, 1)))[0]
    playlist = latest_playlists['playlists'][spotify_playlist_id]
    print(
        f"\tRetrieved data for playlist '{playlist['name']}' - '{playlist['id']}' with '{len(playlist['track_ids'])}' tracks")
    return playlist, len(playlist['track_ids'])


def find_artists_for_genre(genre: str):
    artists = find_many(settings.artists_collection_name, {}, exclude_metadata=True)
    matched_artists = []
    for artist in artists:
        if artist['genres'] and genre in artist['genres']:
            matched_artists.append(artist)

    return matched_artists


def find_all_artists_and_genres():
    artists = find_many(settings.artists_collection_name, {}, select_dict={'_id': 0})
    genres = []
    for artist in artists:
        genres.extend(artist['genres'])

    return {
        'artists': sorted(artists, key=lambda x: x['name']),
        'genres': sorted(list(dict.fromkeys(genres)))
    }


def find_all_tracks():
    tracks = find_many(settings.tracks_collection_name, {})

    return sorted(tracks, key=lambda x: x['name'])


def extract_track_and_store_in_db(track: dict, access_token: str, store=False):
    track_id = track['id']
    new_track = {
        'id': track_id,
        'name': track['name'],
        'artists': [],
        'album_name': track['album']['name'],
        'popularity': track['popularity'],
        'duration_ms': track['duration_ms'],
        'spotify_url': track['external_urls']['spotify'],
        'isrc': track['external_ids']['isrc'],
        'image_url': track['album']['images'][0]['url']
    }
    for artist in track['artists']:
        new_track['artists'].append({'id': artist['id'], 'name': artist['name']})

        if store:
            # also persist artist
            if artist['id'] not in imported_artist_ids:
                url = f"{settings.spotify_artist_url}/{artist['id']}"
                artist_json = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
                store_spotify_artist_data_in_db(artist_json)
    if store:
        if track_id not in imported_track_ids:
            print(f"INFO: Inserting track '{track_id}'")
            update_one(settings.tracks_collection_name, {'_id': track_id}, new_track)
            imported_track_ids.append(track_id)
    return remove_metadata(new_track)


def store_spotify_artist_data_in_db(artist_json: dict, store=True):
    artist_id = artist_json['id']
    db_artist = {
        'id': artist_id,
        'name': artist_json['name'],
        'genres': artist_json['genres'],
        'spotify_url': artist_json['external_urls']['spotify'],
        'followers': artist_json['followers']['total'],
        'popularity': artist_json['popularity'],
    }
    if artist_json['images']:
        db_artist['image_url'] = artist_json['images'][0]['url']
    if store:
        if artist_id not in imported_artist_ids:
            print(f"INFO: Inserting artist '{artist_id}'")
            update_one(settings.artists_collection_name, {'id': artist_id}, db_artist)
            imported_artist_ids.append(artist_id)
    return db_artist
