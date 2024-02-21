from datetime import datetime

from spot_lib_mng import database
from spot_lib_mng.config import settings
from spot_lib_mng.database import extract_track_and_store_in_db, store_spotify_artist_data_in_db
from spot_lib_mng.spotify_api.artists import get_favorite_artists
from spot_lib_mng.spotify_api.token import get_valid_access_token
from spot_lib_mng.spotify_api.tracks import get_favorite_tracks, retrieve_all_tracks_for_playlist
from spot_lib_mng.utils.requests import exec_get_request_with_headers_and_token_and_return_data

total_tracks = 0


def get_spotify_user_id(access_token: str):
    url = "https://api.spotify.com/v1/me"
    response = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
    if 'id' in response:
        return response['id']
    else:
        return ""


def is_owner(access_token: str):
    if get_spotify_user_id(access_token) == settings.spotify_username:
        return True
    return False


def retrieve_spotify_user_data_and_store_in_db(access_token: str):
    # once per day is enough
    latest_document = database.find_latest_documents(settings.most_listened_collection_name, 1)
    if latest_document and latest_document[0]['created_at'].day == datetime.today().day:
        print("WARN: Skipping user data export because latest state is from today...")
        return

    user_data = gather_spotify_user_data(access_token, store=True)

    print(f"SUCCESS: Inserting 'most listened' user data into collection '{settings.most_listened_collection_name}'")
    database.insert_one(settings.most_listened_collection_name, {
        'created_at': datetime.utcnow(),
        'created_by': settings.modifier,
        'data': user_data})
    return user_data


def gather_spotify_user_data(access_token: str, store: bool):
    user_data = {'long_term': {}, 'mid_term': {}, 'short_term': {}}
    # 'long_term' (years), 'medium_term' (6 months) or 'short_term' (4 weeks)

    user_data['long_term']['fav_artists'] = get_favorite_artists(access_token, "long_term", store)
    user_data['mid_term']['fav_artists'] = get_favorite_artists(access_token, "medium_term", store)
    user_data['short_term']['fav_artists'] = get_favorite_artists(access_token, "short_term", store)

    user_data['short_term']['fav_tracks'] = get_favorite_tracks(access_token, "short_term", store)
    user_data['mid_term']['fav_tracks'] = get_favorite_tracks(access_token, "medium_term", store)
    user_data['long_term']['fav_tracks'] = get_favorite_tracks(access_token, "long_term", store)

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
        track = extract_track_and_store_in_db(to_import, access_token, store=True)
        return f"Track '{track['name']}' with id '{track['id']}' has been added to the local library."
    elif type == "artist":
        url = f"{settings.spotify_artist_url}/{id}"
        to_import = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
        artist = store_spotify_artist_data_in_db(to_import, store=True)
        return f"Artist '{artist['name']}' with id '{artist['id']}' has been inserted into the local library."
    elif type == "playlist":
        url = f"{settings.spotify_playlist_url}/{id}"
        playlist_data = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
        playlist = retrieve_all_tracks_for_playlist({},
                                                    playlist_data['tracks'], access_token,
                                                    complete_tracks_and_store=True)
        return f"Playlist '{playlist_data['name']}' with id '{playlist_data['id']}' imported '{playlist['amount_of_tracks']}' tracks into the local library."
