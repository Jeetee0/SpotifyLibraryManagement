import csv
import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import HTTPException

from spot_lib_mng import database
from spot_lib_mng.config import settings
from spot_lib_mng.spotify_api.token import get_valid_access_token
from spot_lib_mng.spotify_api.tracks import retrieve_all_tracks_for_playlist, get_all_tracks_for_spotify_playlist
from spot_lib_mng.utils import requests


def get_current_state_of_spotify_playlists():
    total_amount_of_tracks = 0
    token = get_valid_access_token()
    access_token = token['access_token']
    print(f"INFO: Exporting current state of spotify playlists for user '{settings.spotify_username}'")
    playlists = {}
    if not os.path.exists(settings.csv_playlist_ids_path):
        raise HTTPException(status_code=500, detail=f"CSV file with playlist id's was not existent")
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
            'created_at': datetime.utcnow(),
            'created_by': settings.modifier,
            'playlists': playlists})
        return len(playlists), total_amount_of_tracks


def get_spotify_playlist_by_id(access_token: str, spotify_playlist_id: str):
    # url = f"{settings.spotify_playlist_url}/{spotify_playlist_id}?fields={playlist_url_key_limitations}"
    url = f"{settings.spotify_playlist_url}/{spotify_playlist_id}"
    json = requests.exec_get_request_with_headers_and_token_and_return_data(url, access_token)
    playlist = {
        'id': json['id'],
        'name': json['name'],
        'description': json['description'],
        'owner_id': json['owner']['id'],
        'amount_of_tracks': 0,
        'track_ids': [],
        'spotify_url': json['external_urls']['spotify']
    }
    if 'images' in json and json['images']:
        playlist['image_url'] = json['images'][0]['url']
    playlist = retrieve_all_tracks_for_playlist(playlist, json['tracks'], access_token, complete_tracks_and_store=False)
    print(
        f"\tRetrieved data for playlist '{playlist['name']}' - '{playlist['id']}' with '{len(playlist['track_ids'])}' tracks")
    return playlist, len(playlist['track_ids'])


def get_spotify_playlist_data_raw(spotify_playlist_id: str, access_token: str):
    url = f"{settings.spotify_playlist_url}/{spotify_playlist_id}"
    return requests.exec_get_request_with_headers_and_token_and_return_data(url, access_token)


def add_single_track_to_playlist(playlist_id: str, track_id: str):
    url = f"{settings.spotify_playlist_url}/{playlist_id}/tracks"
    uri = f"spotify:track:{track_id}"
    requests.exec_post_request_with_headers_and_token(url, {'uris': [uri]}, get_valid_access_token()['access_token'])


def add_tracks_to_playlist(playlist_id: str, track_ids: list):
    url = f"{settings.spotify_playlist_url}/{playlist_id}/tracks"
    uris = []
    for track_id in track_ids:
        uris.append(f"spotify:track:{track_id}")
    requests.exec_post_request_with_headers_and_token(url, {'uris': uris}, get_valid_access_token()['access_token'])


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
            artist_json = requests.exec_get_request_with_headers_and_token_and_return_data(url, access_token)
        if 'genres' in artist_json:
            genres = artist_json['genres']
            for genre in genres:
                if genre not in genre_classification:
                    genre_classification[genre] = amount
                else:
                    genre_classification[genre] += amount

        if update_in_db:
            database.store_spotify_artist_data_in_db(artist_json)

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


def update_latest_track_playlists():
    access_token = get_valid_access_token()['access_token']

    if not os.path.exists(settings.csv_latest_tracks_playlists_path):
        raise HTTPException(status_code=500, detail=f"CSV file with latest_track-playlist id's was not existent")
    with open(Path(settings.csv_latest_tracks_playlists_path)) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=';')
        next(csv_reader, None)  # skip the headers

        for row in csv_reader:
            latest_playlist_id = row[0]
            genre_classification = row[1]
            spotify_playlist_ids = row[2]

            if not latest_playlist_id:
                continue

            print(f"INFO: Updating 'Latest-{genre_classification}' playlist with id: '{latest_playlist_id}'")
            newest_track_ids = []
            one_month_ago = datetime.utcnow() - timedelta(days=61)

            for playlist_id in spotify_playlist_ids.split(','):
                playlist = get_spotify_playlist_data_raw(playlist_id, access_token)
                tracks = get_all_tracks_for_spotify_playlist(playlist, access_token)
                for track in tracks:
                    track_id = track['track']['id']
                    added_to_playlist_timestamp = datetime.strptime(track['added_at'], '%Y-%m-%dT%H:%M:%SZ')
                    if added_to_playlist_timestamp > one_month_ago and track_id not in newest_track_ids:
                        # print(f"\t\tTrack added: {track['track']['name']}")
                        newest_track_ids.append(track_id)

            # remove old tracks
            playlist = get_spotify_playlist_data_raw(latest_playlist_id, access_token)
            tracks = get_all_tracks_for_spotify_playlist(playlist, access_token)
            track_ids = [track['track']['id'] for track in tracks]
            remove_tracks_from_spotify_playlist(latest_playlist_id, track_ids, access_token)

            print(f"\tAdding '{len(newest_track_ids)}' tracks")
            add_tracks_to_playlist(latest_playlist_id, newest_track_ids)


def remove_tracks_from_spotify_playlist(playlist_id: str, track_ids: list, access_token: str):
    track_uris = []
    for track_id in track_ids:
        track_uris.append({'uri': f"spotify:track:{track_id}"})

    url = f"{settings.spotify_playlist_url}/{playlist_id}/tracks"
    json_body = {
        'tracks': track_uris
    }
    requests.exec_delete_request_with_headers_and_token(url, json_body, access_token)


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
            backend_host = settings.slm_backend_host
            if settings.slm_backend_port:
                backend_host += ":" + settings.slm_backend_port
            print(f"\t\tNew playlist '{latest_playlist['name']}' was found. Requesting artist data from spotify")
            url = f"{backend_host}/spotify/playlist_genre_classification?playlist_id={playlist_id}"
            requests.exec_get_request_with_headers_and_token_and_return_data(url, access_token)
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
        add_new_tracks_to_spotify_diff_playlist(access_token, new_tracks_diff, all_stored_track_ids)
        database.insert_one(settings.diff_collection_name, {
            'created_at': datetime.utcnow(),
            'created_by': settings.modifier,
            'latest_playlist_state_id': latest_documents[0]['_id'],
            'earlier_playlist_state_id': latest_documents[1]['_id'],
            'new_tracks': new_tracks_diff
        })
    return new_tracks_diff


def add_new_tracks_to_spotify_diff_playlist(access_token: str, new_tracks_diff: dict, all_stored_track_ids: list):
    print(f"\tAdding new tracks to spotify diff playlist...")

    # check which tracks are already in playlist
    diff_playlist, _ = get_spotify_playlist_by_id(access_token, settings.diff_playlist_id)
    existing_track_ids = diff_playlist['track_ids']

    new_track_ids = []
    new_track_id_uris = []
    for _, new_tracks_in_playlist in new_tracks_diff.items():
        for new_track_id in new_tracks_in_playlist:
            if new_track_id not in existing_track_ids and new_track_id not in all_stored_track_ids:
                new_track_id_uris.append(f"spotify:track:{new_track_id}")
                new_track_ids.append(new_track_id)

    length = len(new_track_ids)
    if length > 99:
        print("WARN: New tracks are more then 100. Pagination not implemented yet...")

    if new_track_ids:
        # add tracks to playlist_id
        print(f"\tAdding '{length}' tracks to playlist '{diff_playlist['name']}'")
        url = f"{settings.spotify_playlist_url}/{settings.diff_playlist_id}/tracks"
        requests.exec_post_request_with_headers_and_token(url, {'uris': new_track_id_uris}, access_token)

        if length > 50:
            print(f"WARN: more then 50 new artists in one playlist. cant add all in one request")

        url = f"{settings.spotify_track_url}?ids={','.join(new_track_ids)}"
        new_tracks = requests.exec_get_request_with_headers_and_token_and_return_data(url, access_token)
        for new_track in new_tracks['tracks']:
            new_track = database.extract_track_and_store_in_db(new_track, access_token, store=True)
