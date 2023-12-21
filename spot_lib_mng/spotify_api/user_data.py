import csv
import datetime
from pathlib import Path

import requests

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
        artist = {}
        artist['id'] = item['id']
        artist['name'] = item['name']
        artist['spotify_url'] = item['external_urls']['spotify']
        artist['genres'] = item['genres']
        artist['popularity'] = item['popularity']
        long_term_artists.append(artist)
    return long_term_artists


def get_favorite_tracks(access_token: str, term: str):
    url = f"{settings.spotify_top_user_tracks_url}?time_range={term}&limit=10"
    response_data = exec_get_request_with_headers_and_token_and_return_data(url, access_token)

    items = response_data['items']
    long_term_tracks = []
    for item in items:
        track = {}
        track['id'] = item['id']
        track['name'] = item['name']
        track['artists'] = []
        track['album_name'] = item['album']['name']
        track['popularity'] = item['popularity']
        track['duration_ms'] = item['duration_ms']
        track['spotify_url'] = item['external_urls']['spotify']
        track['isrc'] = item['external_ids']['isrc']

        for artist in item['artists']:
            track['artists'].append(artist['name'])
        long_term_tracks.append(track)
    return long_term_tracks


def exec_get_request_with_headers_and_token_and_return_data(url: str, access_token: str):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.get(url, headers=headers)
    if response.status_code not in [200, 204]:
        print(f"ERROR: Request to {url} was not successful...")
        print(response.text)
        return {}

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
        'track_ids': []
    }
    playlist = retrieve_all_tracks_for_playlist(playlist, json['tracks'], access_token)
    print(
        f"\t\tRetrieved data for playlist '{playlist['name']}' - '{playlist['id']}' with '{len(playlist['track_ids'])}' tracks")
    return playlist, len(playlist['track_ids'])


def retrieve_all_tracks_for_playlist(playlist: dict, current_tracks: list, access_token: str):
    while True:
        for track in current_tracks['items']:
            if not track['track']['id']:
                print(f"WARN: Skipping '{track['track']['name']}' because not available on Spotify (anymore).")
                continue
            new_track = {
                'id': track['track']['id'],
                'name': track['track']['name'],
                'artists': [],
                'album_name': track['track']['album']['name'],
                'popularity': track['track']['popularity'],
                'duration_ms': track['track']['duration_ms'],
                'spotify_url': track['track']['external_urls']['spotify'],
                'isrc': track['track']['external_ids']['isrc']
            }
            for artist in track['track']['artists']:
                new_track['artists'].append({'id': artist['id'], 'name': artist['name']})
            database.update_one(settings.tracks_collection_name, {'_id': new_track['id']}, new_track)
            playlist['track_ids'].append(new_track['id'])

        # track amount limit per call is 100, so check for more tracks
        if 'next' not in current_tracks or not current_tracks['next']:
            playlist['amount_of_tracks'] = len(playlist['track_ids'])
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
            print(f"\t\tNew playlist '{latest_playlist['name']}' was found.")
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
