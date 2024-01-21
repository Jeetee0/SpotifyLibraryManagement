import csv
import datetime
import json
from pathlib import Path
from bson.json_util import dumps
from urllib.request import urlretrieve
from urllib.parse import quote, urlencode

import requests
from fastapi import HTTPException

from spot_lib_mng import database
from spot_lib_mng.config import settings
from spot_lib_mng.spotify_api.token import get_valid_access_token

playlist_url_key_limitations = "description,name,id,owner,tracks(items(track(id,album,artists,duration_ms,external_ids,external_urls,name,popularity)),next)"
tracks_url_key_limitations = "items(track(id,album,artists,duration_ms,external_ids,external_urls,name,popularity)),next"
db = database.get_db()
total_tracks = 0


def retrieve_spotify_user_data():
    # once per day is enough
    latest_document = database.find_latest_documents(settings.most_listened_collection_name, 1)
    if latest_document and latest_document[0]['created_at'].day == datetime.datetime.today().day:
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
        'created_at': datetime.datetime.utcnow(),
        'created_by': settings.modifier,
        'data': user_data})
    return user_data


def get_favorite_artists(access_token: str, term: str):
    url = f"{settings.spotify_top_user_artists_url}?time_range={term}&limit=10"
    response_data = exec_get_request_with_headers_and_token_and_return_data(url, access_token)

    items = response_data['items']
    long_term_artists = []
    for item in items:
        artist = store_spotify_artist_data_in_db(item)
        long_term_artists.append(artist)
    return long_term_artists


def get_favorite_tracks(access_token: str, term: str):
    url = f"{settings.spotify_top_user_tracks_url}?time_range={term}&limit=10"
    response_data = exec_get_request_with_headers_and_token_and_return_data(url, access_token)

    items = response_data['items']
    long_term_tracks = []
    for item in items:
        track = store_spotify_track_in_db(item, access_token)
        long_term_tracks.append(track)
    return long_term_tracks


def get_current_state_of_spotify_playlists():
    total_amount_of_tracks = 0
    token = get_valid_access_token()
    access_token = token['access_token']
    print(f"INFO: Exporting current state of spotify playlists for user '{settings.spotify_username}'")
    playlists = {}
    with open(Path(settings.csv_playlist_ids_path)) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=';')
        next(csv_reader, None)  # skip the headers
        for row in csv_reader:
            playlist_name = row[0]
            folder_name = row[1]
            spotify_playlist_id = row[2]

            if not playlist_name:
                continue

            playlist, amount_of_tracks = get_spotify_playlist_by_id(access_token, spotify_playlist_id)
            playlist['folder'] = folder_name
            playlists[playlist['id']] = playlist
            total_amount_of_tracks += amount_of_tracks

        print(f"SUCCESS: Inserting '{len(playlists)}' playlists to collection '{settings.playlist_collection_name}'")
        database.insert_one(settings.playlist_collection_name, {
            'created_at': datetime.datetime.utcnow(),
            'created_by': settings.modifier,
            'playlists': playlists})
        return len(playlists), total_amount_of_tracks


def get_spotify_playlist_by_id(access_token: str, spotify_playlist_id: str):
    # url = f"{settings.spotify_playlist_url}/{spotify_playlist_id}?fields={playlist_url_key_limitations}"
    url = f"{settings.spotify_playlist_url}/{spotify_playlist_id}"
    json = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
    playlist = {
        'id': json['id'],
        'name': json['name'],
        'description': json['description'],
        'owner_id': json['owner']['id'],
        'amount_of_tracks': 0,
        'track_ids': [],
        'spotify_url': json['external_urls']['spotify']
    }
    if 'images' in json:
        playlist['image_url'] = json['images'][0]['url']
    playlist = retrieve_all_tracks_for_playlist(playlist, json['tracks']['items'], access_token)
    print(
        f"\tRetrieved data for playlist '{playlist['name']}' - '{playlist['id']}' with '{len(playlist['track_ids'])}' tracks")
    return playlist, len(playlist['track_ids'])


def retrieve_all_tracks_for_playlist(playlist: dict, current_tracks: list, access_token: str = None, complete_tracks=False):
    if complete_tracks:
        playlist['tracks'] = []

    while True:
        for track in current_tracks:
            if 'track' in track:
                track = track['track']
            if not track['id']:
                print(f"WARN: Skipping '{track['name']}' because not available on Spotify (anymore).")
                continue
            new_track = store_spotify_track_in_db(track, access_token)

            if complete_tracks:
                playlist['tracks'].append(new_track)
            else:
                playlist['track_ids'].append(new_track['id'])

        # track amount limit per call is 100, so check for more tracks
        if 'next' not in current_tracks or not current_tracks['next']:
            playlist['amount_of_tracks'] = len(playlist['tracks']) if complete_tracks else len(playlist['track_ids'])
            return playlist

        # url = f"{current_tracks['next']}&fields={tracks_url_key_limitations}"
        url = f"{current_tracks['next']}"
        current_tracks = exec_get_request_with_headers_and_token_and_return_data(url, access_token)


def create_diff_between_latest_playlist_states():
    token = get_valid_access_token()
    access_token = token['access_token']
    latest_documents = database.find_latest_documents(settings.playlist_collection_name, 2)
    latest_diff = database.find_latest_documents(settings.diff_collection_name, 1)
    if len(latest_documents) < 2:
        print("ERROR: Can't create diff because only one playlist state is existing...")
        return

    if latest_diff and latest_diff[0]['latest_playlist_state_id'] == latest_documents[0]['_id'] and latest_diff[0][
        'earlier_playlist_state_id'] == latest_documents[1]['_id']:
        print(f"WARN: Diff for latest playlist states was already created. Aborting...")
        return

    print(f"INFO: Creating diff of spotify playlist state between two latest states...")
    latest_state_of_playlists = latest_documents[0]['playlists']
    earlier_state_of_playlists = latest_documents[1]['playlists']
    new_tracks_diff = {}
    all_stored_track_ids = []
    for _, earlier_playlist in earlier_state_of_playlists.items():
        all_stored_track_ids.extend(earlier_playlist['track_ids'])
    all_stored_track_ids = list(dict.fromkeys(all_stored_track_ids))

    for playlist_id, latest_playlist in latest_state_of_playlists.items():
        new_tracks_for_playlist = []
        if playlist_id not in earlier_state_of_playlists:
            print(f"\t\tNew playlist '{latest_playlist['name']}' was found. Requesting artist data from spotify")
            url = f"http://localhost:9090/spotify/playlist_genre_classification?playlist_id={playlist_id}"
            exec_get_request_with_headers_and_token_and_return_data(url, access_token)
            new_tracks_for_playlist.extend(latest_playlist['track_ids'])
        else:
            tracks_before = earlier_state_of_playlists[playlist_id]['track_ids']
            for track_id in latest_playlist['track_ids']:
                if track_id not in tracks_before:
                    new_tracks_for_playlist.append(track_id)

        if len(new_tracks_for_playlist):
            print(f"\t\tFound '{len(new_tracks_for_playlist)}' new track(s) for playlist '{latest_playlist['name']}'")
            new_tracks_diff[latest_playlist['name']] = new_tracks_for_playlist

    if new_tracks_diff:
        database.insert_one(settings.diff_collection_name, {
            'created_at': datetime.datetime.utcnow(),
            'created_by': settings.modifier,
            'latest_playlist_state_id': latest_documents[0]['_id'],
            'earlier_playlist_state_id': latest_documents[1]['_id'],
            'new_tracks': new_tracks_diff
        })
        add_tracks_to_spotify_playlist(access_token, new_tracks_diff, all_stored_track_ids)
    return new_tracks_diff


def add_tracks_to_spotify_playlist(access_token: str, new_tracks_diff: dict, all_stored_track_ids: list):
    print(f"\tAdding new tracks to spotify diff playlist...")

    # check which tracks are already in playlist
    diff_playlist, _ = get_spotify_playlist_by_id(access_token, settings.diff_playlist_id)
    existing_track_ids = diff_playlist['track_ids']

    new_track_ids = []
    for _, new_tracks_in_playlist in new_tracks_diff.items():
        for new_track_id in new_tracks_in_playlist:
            if new_track_id not in existing_track_ids and new_track_id not in all_stored_track_ids:
                new_track_ids.append(f"spotify:track:{new_track_id}")

    if len(new_track_ids) > 99:
        print("WARN: New tracks are more then 100. Pagination not implemented yet...")

    if len(new_track_ids):
        # add tracks to playlist_id
        print(f"\tAdding '{len(new_track_ids)}' tracks to playlist '{diff_playlist['name']}'")
        url = f"{settings.spotify_playlist_url}/{settings.diff_playlist_id}/tracks"
        exec_post_request_with_headers_and_token(url, {'uris': new_track_ids}, access_token)


def add_single_track_to_playlist(playlist_id: str, track_id: str):
    url = f"{settings.spotify_playlist_url}/{playlist_id}/tracks"
    uri = f"spotify:track:{track_id}"
    exec_post_request_with_headers_and_token(url, {'uris': [uri]}, get_valid_access_token()['access_token'])


def add_to_default_playlist(playlist_index: str, track_id: str):
    if playlist_index == "1":
        playlist_id = settings.spotify_playlist_link_1
    elif playlist_index == "2":
        playlist_id = settings.spotify_playlist_link_2
    else:
        raise HTTPException(status_code=500, detail=f"You can only add to default playlist with index '1' & '2'")
    add_single_track_to_playlist(playlist_id, track_id)
    return {'playlist_id': playlist_id, 'track_id': track_id}


def classify_spotify_playlist_with_genres(playlist_id: str, update_in_db=True, enriched_info=True):
    genre_classification = {}
    artist_dict = {}
    token = get_valid_access_token()
    access_token = token['access_token']

    if update_in_db:
        playlist, amount_of_tracks = get_spotify_playlist_by_id(access_token, playlist_id)
    else:
        print("correct")
        playlist, amount_of_tracks = database.get_latest_playlist_by_id(playlist_id)
    print(f"INFO: Getting genres for spotify playlist with id '{playlist_id}' and '{amount_of_tracks}' tracks")
    tracks = database.find_many(settings.tracks_collection_name, {'_id': {'$in': playlist['track_ids']}})
    for track in tracks:
        for artist in track['artists']:
            if artist['id'] not in artist_dict:
                artist_dict[artist['id']] = {
                    'name': artist['name'],
                    'amount': 1
                }
            else:
                artist_dict[artist['id']]['amount'] += 1

    for artist_id in artist_dict:
        amount = artist_dict[artist_id]['amount']
        artist_json = {}
        if not update_in_db:
            artist_json = database.find_one(settings.artists_collection_name, {'id': artist_id})
        if not artist_json or update_in_db:
            url = f"{settings.spotify_artist_url}/{artist_id}"
            artist_json = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
        if 'genres' in artist_json:
            genres = artist_json['genres']
            for genre in genres:
                if genre not in genre_classification:
                    genre_classification[genre] = amount
                else:
                    genre_classification[genre] += amount

        if update_in_db:
            store_spotify_artist_data_in_db(artist_json)

    result = {
        'unique_artists': len(artist_dict.keys()),
        'unique_genres': len(genre_classification.keys()),
        'genres': dict(sorted(genre_classification.items(), key=lambda item: item[1], reverse=True)),
        'artists': dict(sorted(artist_dict.items(), key=lambda item: item[1]['amount'], reverse=True))
    }
    if enriched_info:
        result['spotify_playlist_name'] = playlist['name']
        result['spotify_playlist_id'] = playlist_id
        result['amount_of_tracks'] = amount_of_tracks
        result['artists'] = dict(sorted(artist_dict.items(), key=lambda item: item[1]['amount'], reverse=True))
    return result


def discover_new_tracks(genres: str, artists: str, tracks: str, limit: int, market: str = None):
    access_token = get_valid_access_token()['access_token']
    query_strings = {
        'limit': limit,
        'market': market,

        'seed_artists': convert_query_param_string(artists),
        'seed_genres': convert_query_param_string(genres),
        'seed_tracks': convert_query_param_string(tracks),


    }
    query_strings = {k: v for k, v in query_strings.items() if v is not None}

    url = settings.spotify_recommendations_url + '?'
    for query_string_key in query_strings:
        url += f"{query_string_key}={query_strings[query_string_key]}&"

    response_json = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
    return retrieve_all_tracks_for_playlist({}, response_json['tracks'], access_token, complete_tracks=True)

########################## usability ###################################


def convert_query_param_string(incoming: str):
    return incoming.replace(' ', '+').replace(',', '%2C')


def store_spotify_track_in_db(track: dict, access_token: str):
    new_track = {
        'id': track['id'],
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

        # also persist artist
        url = f"{settings.spotify_artist_url}/{artist['id']}"
        artist_json = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
        store_spotify_artist_data_in_db(artist_json)
    database.update_one(settings.tracks_collection_name, {'_id': new_track['id']}, new_track)
    return remove_metadata(new_track)


def store_spotify_artist_data_in_db(artist_json: dict):
    db_artist = {
        'name': artist_json['name'],
        'genres': artist_json['genres'],
        'spotify_url': artist_json['external_urls']['spotify'],
        'followers': artist_json['followers']['total'],
        'popularity': artist_json['popularity'],
    }
    if artist_json['images']:
        db_artist['image_url'] = artist_json['images'][0]['url']
    database.update_one(settings.artists_collection_name, {'id': artist_json['id']}, db_artist)
    return db_artist


def exec_get_request_with_headers_and_token_and_return_data(url: str, access_token: str):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 429:
        print(response.headers)
        raise HTTPException(status_code=429, detail=f"Too many requests to spotify API. Retry again in: {int(response.headers['retry-after'])/60} mins")
    elif response.status_code not in [200, 204]:
        raise HTTPException(status_code=500,
                            detail=f"Request to {url} was not successful. Error: {response.status_code} - {response.text}")

    return response.json()


def exec_post_request_with_headers_and_token(url: str, body: dict, access_token: str):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.post(url, json=body, headers=headers)
    if response.status_code not in [200, 201, 204]:
        print(f"ERROR: Request to {url} was not successful...")
        print(response.text)
        return {}

    return response.status_code


def remove_metadata(db_item, with_mongo_id=False):
    if 'modified_at' in db_item:
        del db_item['modified_at']
    if 'modified_by' in db_item:
        del db_item['modified_by']
    if 'created_at' in db_item:
        del db_item['created_at']
    if 'created_by' in db_item:
        del db_item['created_by']

    if with_mongo_id and '_id' in db_item:
        del db_item['_id']
    return db_item



# dev manual
def exec_manual_script():
    return_data = {}
    data = json.loads(dumps(database.find_max(settings.artists_collection_name, "popularity", 5)))
    popu_list = []
    for element in data:
        popu_list.append({
            'popularity': element['popularity'],
            'name': element['name'],
            'followers': element['followers'],
            'genres': element['genres']
        })
    return_data['highest_popularity'] = popu_list

    data = json.loads(dumps(database.find_max(settings.artists_collection_name, "followers", 5)))
    follow_list = []
    for element in data:
        follow_list.append({
            'popularity': element['popularity'],
            'name': element['name'],
            'followers': element['followers'],
            'genres': element['genres']
        })
    return_data['highest_followers'] = follow_list
    return return_data
    # token = get_valid_access_token()
    # access_token = token['access_token']
    #
    # with open(Path("./spotify_playlist_ids_2.csv")) as csv_file:
    #     csv_reader = csv.reader(csv_file, delimiter=';')
    #     next(csv_reader, None)  # skip the headers
    #     for row in csv_reader:
    #         playlist_name = row[0]
    #         folder_name = row[1]
    #         spotify_playlist_id = row[2]
    #         if not playlist_name:
    #             continue
    #
    #         url = f"http://localhost:9093/spotify/playlist_genre_classification?playlist_id={spotify_playlist_id}"
    #         response_data = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
