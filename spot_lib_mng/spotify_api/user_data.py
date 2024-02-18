from datetime import datetime

from spot_lib_mng import database
from spot_lib_mng.config import settings
from spot_lib_mng.database import extract_track_and_store_in_db, store_spotify_artist_data_in_db
from spot_lib_mng.utils.requests import exec_get_request_with_headers_and_token_and_return_data
from spot_lib_mng.spotify_api.artists import get_favorite_artists
from spot_lib_mng.spotify_api.token import get_valid_access_token
from spot_lib_mng.spotify_api.tracks import get_favorite_tracks, retrieve_all_tracks_for_playlist


total_tracks = 0


def retrieve_spotify_user_data():
    # once per day is enough
    latest_document = database.find_latest_documents(settings.most_listened_collection_name, 1)
    if latest_document and latest_document[0]['created_at'].day == datetime.today().day:
        print("WARN: Skipping user data export because latest state is from today...")
        return

    token = get_valid_access_token()
    access_token = token['access_token']
    user_data = {}

    # 'long_term' (years), 'medium_term' (6 months) or 'short_term' (4 weeks)
    user_data['long_term'] = {}
    user_data['mid_term'] = {}
    user_data['short_term'] = {}

    user_data['long_term']['fav_artists'] = get_favorite_artists(access_token, "long_term")
    user_data['mid_term']['fav_artists'] = get_favorite_artists(access_token, "medium_term")
    user_data['short_term']['fav_artists'] = get_favorite_artists(access_token, "short_term")

    user_data['short_term']['fav_tracks'] = get_favorite_tracks(access_token, "short_term")
    user_data['mid_term']['fav_tracks'] = get_favorite_tracks(access_token, "medium_term")
    user_data['long_term']['fav_tracks'] = get_favorite_tracks(access_token, "long_term")

    print(f"SUCCESS: Inserting 'most listened' user data into collection '{settings.most_listened_collection_name}'")
    database.insert_one(settings.most_listened_collection_name, {
        'created_at': datetime.utcnow(),
        'created_by': settings.modifier,
        'data': user_data})
    return user_data


def start_spotify_search(term: str, type: str):
    access_token = get_valid_access_token()['access_token']
    url = f"{settings.spotify_search_url}?q={term}&type={type}&limit=20"
    response = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
    return_items = []
    if type == "track":
        for track in response['tracks']['items']:
            return_items.append(extract_track_and_store_in_db(track, access_token, store=False))
    elif type == "artist":
        for artist in response['artists']['items']:
            return_items.append(store_spotify_artist_data_in_db(artist, store=False))
    elif type == "playlist":
        return_items = response['playlists']['items']
    return return_items


def import_item_from_spotify(id: str, type: str):
    access_token = get_valid_access_token()['access_token']
    if type == "track":
        url = f"{settings.spotify_track_url}/{id}"
        to_import = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
        return extract_track_and_store_in_db(to_import, access_token, store=True)
    elif type == "artist":
        url = f"{settings.spotify_artist_url}/{id}"
        to_import = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
        return store_spotify_artist_data_in_db(to_import, store=True)
    elif type == "playlist":
        url = f"{settings.spotify_playlist_url}/{id}"
        playlist_data = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
        return retrieve_all_tracks_for_playlist({}, playlist_data['tracks'], access_token,
                                                complete_tracks_and_store=True)
