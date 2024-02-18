from spot_lib_mng.config import settings
from spot_lib_mng.spotify_api.token import get_valid_access_token
from spot_lib_mng.database import extract_track_and_store_in_db
from spot_lib_mng.utils.requests import exec_get_request_with_headers_and_token_and_return_data
from spot_lib_mng.utils.utils import convert_query_param_string


def get_favorite_tracks(access_token: str, term: str):
    url = f"{settings.spotify_top_user_tracks_url}?time_range={term}&limit=10"
    response_data = exec_get_request_with_headers_and_token_and_return_data(url, access_token)

    items = response_data['items']
    long_term_tracks = []
    for item in items:
        track = extract_track_and_store_in_db(item, access_token, store=True)
        long_term_tracks.append(track)
    return long_term_tracks


def get_all_tracks_for_spotify_playlist(playlist: dict, access_token: str):
    gathered_tracks = []
    current_tracks = playlist['tracks']
    while True:
        for track in current_tracks['items']:
            if 'track' in track and 'id' in track['track']:
                gathered_tracks.append(track)

        # track amount limit per call is 100, so check for more tracks
        if 'next' not in current_tracks or not current_tracks['next']:
            return gathered_tracks

        url = f"{current_tracks['next']}"
        current_tracks = exec_get_request_with_headers_and_token_and_return_data(url, access_token)


def retrieve_all_tracks_for_playlist(playlist: dict, current_tracks: list, access_token: str = None,
                                     complete_tracks_and_store=False):
    if complete_tracks_and_store:
        playlist['tracks'] = []

    while True:
        if 'items' in current_tracks:  # in playlists there is another layer with 'items'. also needed for pagination
            items = current_tracks['items']
        else:
            items = current_tracks
        for track in items:
            if 'track' in track:
                track = track['track']
            if not track['id']:
                print(f"WARN: Skipping '{track['name']}' because not available on Spotify (anymore).")
                continue
            new_track = extract_track_and_store_in_db(track, access_token, complete_tracks_and_store)

            if complete_tracks_and_store:
                playlist['tracks'].append(new_track)
            else:
                playlist['track_ids'].append(new_track['id'])

        # track amount limit per call is 100, so check for more tracks
        if 'next' not in current_tracks or not current_tracks['next']:
            playlist['amount_of_tracks'] = len(playlist['tracks']) if complete_tracks_and_store else len(
                playlist['track_ids'])
            return playlist

        # url = f"{current_tracks['next']}&fields={tracks_url_key_limitations}"
        url = f"{current_tracks['next']}"
        current_tracks = exec_get_request_with_headers_and_token_and_return_data(url, access_token)


def retrieve_track_features(track_id: str):
    url = f"{settings.spotify_track_features_url}/{track_id}"
    return exec_get_request_with_headers_and_token_and_return_data(url, get_valid_access_token()['access_token'])


def discover_new_tracks(query_strings: dict):
    access_token = get_valid_access_token()['access_token']

    # remove none values
    query_strings = {k: v for k, v in query_strings.items() if v is not None and v != ""}

    url = settings.spotify_recommendations_url + '?'
    for query_string_key in query_strings:
        value = query_strings[query_string_key]
        if isinstance(value, str):
            value = convert_query_param_string(value)
        url += f"{query_string_key}={value}&"
    url = url[:-1]

    response_json = exec_get_request_with_headers_and_token_and_return_data(url, access_token)
    if 'tracks' not in response_json or not response_json['tracks']:
        print("ERROR: No 'tracks' key was present:")
        print(response_json)
        return {'tracks': []}
    return retrieve_all_tracks_for_playlist({}, response_json['tracks'], access_token, complete_tracks_and_store=True)
