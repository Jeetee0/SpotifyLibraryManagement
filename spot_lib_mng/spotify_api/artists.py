from spot_lib_mng import database
from spot_lib_mng.config import settings
from spot_lib_mng.spotify_api.token import get_valid_access_token
from spot_lib_mng.utils.requests import exec_get_request_with_headers_and_token_and_return_data


def find_artists_with_highest_popularity_and_most_followers():
    return {
        'highest_popularity': list(database.find_max(settings.artists_collection_name, "popularity", 20)),
        'most_followers': list(database.find_max(settings.artists_collection_name, "followers", 20))
    }


def get_favorite_artists(access_token: str, term: str):
    url = f"{settings.spotify_top_user_artists_url}?time_range={term}&limit=10"
    response_data = exec_get_request_with_headers_and_token_and_return_data(url, access_token)

    items = response_data['items']
    long_term_artists = []
    for item in items:
        artist = database.store_spotify_artist_data_in_db(item)
        long_term_artists.append(artist)
    return long_term_artists


def get_top_tracks_for_artist(artist_id: str):
    access_token = get_valid_access_token()['access_token']
    url = f"{settings.spotify_artist_url}/{artist_id}/top-tracks?market=DE"
    response = exec_get_request_with_headers_and_token_and_return_data(url, get_valid_access_token()['access_token'])
    tracks = []
    if not response:
        return tracks
    for spoti_track in response['tracks']:
        tracks.append(database.extract_track_and_store_in_db(spoti_track, access_token, store=True))
    return tracks


def get_related_artists(artist_id: str):
    url = f"{settings.spotify_artist_url}/{artist_id}/related-artists"
    response = exec_get_request_with_headers_and_token_and_return_data(url, get_valid_access_token()['access_token'])
    artists = []
    if not response:
        return artists
    for rel_artists in response['artists']:
        artists.append(database.store_spotify_artist_data_in_db(rel_artists))
    return artists


def get_followed_artists():
    url = f"{settings.spotify_user_artist_following_url}?type=artist&limit=50"
    response = exec_get_request_with_headers_and_token_and_return_data(url, get_valid_access_token()['access_token'])
    artists = response['artists']['items']
    next = response['artists']['next']
    if next:
        response = exec_get_request_with_headers_and_token_and_return_data(next,
                                                                           get_valid_access_token()['access_token'])

        artists.extend(response['artists']['items'])
    resulting_artists = []
    for artist in artists:
        resulting_artists.append(database.store_spotify_artist_data_in_db(artist))
    return resulting_artists
