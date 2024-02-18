import json
import re

from bson.json_util import dumps
from fastapi import APIRouter
from starlette.status import HTTP_200_OK

from spot_lib_mng import database
from spot_lib_mng.config import settings
from spot_lib_mng.spotify_api.token import get_new_access_token_from_spotify, evaluate_spotify_return_code
from spot_lib_mng.spotify_api.user_data import retrieve_spotify_user_data, start_spotify_search, import_item_from_spotify
from spot_lib_mng.spotify_api.tracks import retrieve_track_features, discover_new_tracks
from spot_lib_mng.spotify_api.playlists import get_current_state_of_spotify_playlists, add_to_default_playlist, \
    classify_spotify_playlist_with_genres, update_latest_track_playlists, create_diff_between_latest_playlist_states
from spot_lib_mng.spotify_api.artists import find_artists_with_highest_popularity_and_most_followers, \
    get_top_tracks_for_artist, get_related_artists, get_followed_artists

router = APIRouter()
db = database.get_db()


@router.get("/request_access_token", status_code=HTTP_200_OK, tags=["login"])
def request_access_token():
    get_new_access_token_from_spotify()


@router.get("/retrieve_code", status_code=HTTP_200_OK, tags=["login"],
            description="Is used by Spotify and should not be called by a user")
def retrieve_code(code: str):
    token = evaluate_spotify_return_code(code)
    database.store_access_token(token)
    return {'status': 'SUCCESS', 'info': "Token was stored in DB. You can now retrieve your personal spotify data"}


@router.get("/trigger_complete_data_retrieval", status_code=HTTP_200_OK, tags=["spotify"])
def trigger_complete_data_retrieval():
    retrieve_spotify_user_data()
    playlists_count, tracks_count = get_current_state_of_spotify_playlists()
    create_diff_between_latest_playlist_states()
    update_latest_track_playlists()
    return {"status": "success", 'amount_of_playlists': playlists_count,
            'total_amount_of_tracks_in_playlists': tracks_count}


@router.get("/latest_user_data_states", status_code=HTTP_200_OK, tags=["spotify"])
def latest_user_data_states(amount: int = 1):
    return json.loads(dumps(database.find_latest_documents(settings.most_listened_collection_name, amount)))


@router.get("/latest_playlist_states", status_code=HTTP_200_OK, tags=["playlist"])
def latest_playlist_states(amount: int = 1):
    return json.loads(dumps(database.find_latest_documents(settings.playlist_collection_name, amount)))


@router.get("/latest_diff_states", status_code=HTTP_200_OK, tags=["playlist"])
def latest_diff_states(amount: int = 1):
    return json.loads(dumps(database.find_latest_documents(settings.diff_collection_name, amount)))


@router.get("/playlists_by_ids", status_code=HTTP_200_OK, tags=["playlist"])
def playlists_by_ids(ids: str):
    id_list = ids.split(',')
    latest_playlists = json.loads(dumps(database.find_latest_documents(settings.playlist_collection_name, 1)))[0]

    selected_playlists = []
    for playlist_key in latest_playlists['playlists']:
        if playlist_key in id_list:
            curr_playlist = latest_playlists['playlists'][playlist_key]
            curr_playlist['genre_classification'] = classify_spotify_playlist_with_genres(playlist_key,
                                                                                          update_in_db=False,
                                                                                          enriched_info=False)
            selected_playlists.append(curr_playlist)

    return selected_playlists


@router.get("/playlist_genre_classification", status_code=HTTP_200_OK, tags=["playlist"])
def classify_genres_for_playlist(playlist_id: str):
    return classify_spotify_playlist_with_genres(playlist_id)


@router.post("/add_to_default_playlists", status_code=HTTP_200_OK, tags=["playlist"])
def add_to_playlist(playlist_index, track_id):
    return add_to_default_playlist(playlist_index, track_id)


@router.get("/artists_and_genres", status_code=HTTP_200_OK, tags=["artist"])
def tracks():
    return database.find_all_artists_and_genres()


@router.get("/artist_by_id", status_code=HTTP_200_OK, tags=["artist"])
def artist_by_id(artist_id: str):
    return database.find_one(settings.artists_collection_name, {'id': artist_id}, exclude_metadata=True)


@router.get("/artists_by_ids", status_code=HTTP_200_OK, tags=["artist"])
def artists_by_ids(artist_ids: str):
    regex_list = [re.compile(term, re.IGNORECASE) for term in artist_ids.split(',')]
    return database.find_many(settings.artists_collection_name, {'id': {'$in': regex_list}}, exclude_metadata=True)


@router.get("/artists_by_name", status_code=HTTP_200_OK, tags=["artist"])
def artists_by_names(names: str):
    regex_list = [re.compile(term, re.IGNORECASE) for term in names.split(',')]
    return database.find_many(settings.artists_collection_name, {'name': {'$in': regex_list}}, exclude_metadata=True)


@router.get("/artist_top_tracks", status_code=HTTP_200_OK, tags=["artist"])
def top_tracks_for_artist(artist_id: str):
    return get_top_tracks_for_artist(artist_id)


@router.get("/related_artists", status_code=HTTP_200_OK, tags=["artist"])
def related_artists(artist_id: str):
    return get_related_artists(artist_id)


@router.get("/followed_artists", status_code=HTTP_200_OK, tags=["artist"])
def followed_artists():
    return get_followed_artists()


@router.get("/artists_for_genre", status_code=HTTP_200_OK, tags=["artist"])
def get_artists_for_genre(genre: str):
    return database.find_artists_for_genre(genre)


@router.get("/tracks", status_code=HTTP_200_OK, tags=["track"])
def tracks():
    return database.find_all_tracks()


@router.get("/tracks_by_ids", status_code=HTTP_200_OK, tags=["track"])
def tracks_by_ids(ids: str):
    id_list = ids.split(',')
    result = database.find_many(settings.tracks_collection_name, {'_id': {'$in': id_list}})
    sorted_data = sorted(result, key=lambda x: id_list.index(x['_id']), reverse=True)
    return sorted_data


@router.get("/track_features", status_code=HTTP_200_OK, tags=["track"])
def track_features(track_id: str):
    return retrieve_track_features(track_id)


@router.get("/discover", status_code=HTTP_200_OK, tags=["track"])
def discover(genres: str, artists: str, tracks: str,
             limit: int = 20, market: str = None,
             min_popularity: int = None, max_popularity: int = None, target_popularity: int = None,
             min_tempo: int = None, max_tempo: int = None, target_tempo: int = None,
             min_energy: float = None, max_energy: float = None, target_energy: int = None,
             min_key: int = None, max_key: int = None, target_key: int = None,
             min_danceability: float = None, max_danceability: float = None, target_danceability: float = None,
             min_mode: int = None, max_mode: int = None, target_mode: int = None
             ):
    # todo validate fields
    parameter_dict = {
        'seed_genres': genres,
        'seed_artists': artists,
        'seed_tracks': tracks,

        'limit': limit,
        'market': market,

        'min_popularity': min_popularity,
        'max_popularity': max_popularity,
        'target_popularity': target_popularity,
        'min_tempo': min_tempo,
        'max_tempo': max_tempo,
        'target_tempo': target_tempo,
        'min_energy': min_energy,
        'max_energy': max_energy,
        'target_energy': target_energy,
        'min_key': min_key,
        'max_key': max_key,
        'target_key': target_key,
        'min_danceability': min_danceability,
        'max_danceability': max_danceability,
        'target_danceability': target_danceability,
        'min_mode': min_mode,
        'max_mode': max_mode,
        'target_mode': target_mode
    }
    return discover_new_tracks(parameter_dict)


@router.get("/general_search", status_code=HTTP_200_OK, tags=["spotify"])
def search_at_spotify(term: str, type: str):
    if term == "":
        return {}
    if type != "artist" and type != "track" and type != "playlist":
        return {}
    return start_spotify_search(term, type)


@router.post("/import_item", status_code=HTTP_200_OK, tags=["spotify"])
def import_item(id: str, type: str):
    if id == "":
        return {}
    if type != "artist" and type != "track" and type != "playlist":
        return {}
    return import_item_from_spotify(id, type)


@router.get("/highest_artist_stats", status_code=HTTP_200_OK, tags=["artist"])
def highest_artist_stats():
    return find_artists_with_highest_popularity_and_most_followers()
