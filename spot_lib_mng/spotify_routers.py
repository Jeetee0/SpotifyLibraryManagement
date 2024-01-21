import json
import re

from bson.json_util import dumps
from fastapi import APIRouter
from starlette.status import HTTP_200_OK, HTTP_204_NO_CONTENT

from spot_lib_mng.config import settings
from spot_lib_mng.database import store_access_token, find_many, find_latest_documents, find_artists_for_genre, \
    find_all_genres, find_all_artists, find_all_tracks
from spot_lib_mng.spotify_api.token import get_access_token, evaluate_spotify_return_code
from spot_lib_mng.spotify_api.user_data import retrieve_spotify_user_data, get_current_state_of_spotify_playlists, \
    create_diff_between_latest_playlist_states, classify_spotify_playlist_with_genres, exec_manual_script, \
    discover_new_tracks, add_to_default_playlist

router = APIRouter()


@router.get("/request_access_token", status_code=HTTP_200_OK, tags=["spotify"])
def request_access_token():
    get_access_token()


@router.get("/retrieve_code", status_code=HTTP_200_OK, tags=["spotify"],
            description="Is used by Spotify and should not be called by a user")
def retrieve_code(code: str):
    token = evaluate_spotify_return_code(code)
    store_access_token(token)
    return {'status': 'SUCCESS', 'info': "Token was stored in DB. You can now retrieve your personal spotify data"}


@router.get("/trigger_complete_data_retrieval", status_code=HTTP_200_OK, tags=["spotify"])
def trigger_complete_data_retrieval():
    retrieve_spotify_user_data()
    playlists_count, tracks_count = get_current_state_of_spotify_playlists()
    create_diff_between_latest_playlist_states()
    return {"status": "success", 'amount_of_playlists': playlists_count,
            'total_amount_of_tracks_in_playlists': tracks_count}


@router.get("/latest_playlist_states", status_code=HTTP_200_OK, tags=["spotify"])
def latest_playlist_states(amount: int = 1):
    return json.loads(dumps(find_latest_documents(settings.playlist_collection_name, amount)))


@router.get("/latest_diff_states", status_code=HTTP_200_OK, tags=["spotify"])
def latest_diff_states(amount: int = 1):
    return json.loads(dumps(find_latest_documents(settings.diff_collection_name, amount)))


@router.get("/latest_user_data_states", status_code=HTTP_200_OK, tags=["spotify"])
def latest_user_data_states(amount: int = 1):
    return json.loads(dumps(find_latest_documents(settings.most_listened_collection_name, amount)))


@router.get("/tracks_by_ids", status_code=HTTP_200_OK, tags=["spotify"])
def tracks_by_ids(ids: str):
    id_list = ids.split(',')
    result = find_many(settings.tracks_collection_name, {'_id': {'$in': id_list}})
    sorted_data = sorted(result, key=lambda x: id_list.index(x['_id']), reverse=True)
    return sorted_data


@router.get("/playlists_by_ids", status_code=HTTP_200_OK, tags=["spotify"])
def playlists_by_ids(ids: str):
    id_list = ids.split(',')
    latest_playlists = json.loads(dumps(find_latest_documents(settings.playlist_collection_name, 1)))[0]

    selected_playlists = []
    for playlist_key in latest_playlists['playlists']:
        if playlist_key in id_list:
            curr_playlist = latest_playlists['playlists'][playlist_key]
            curr_playlist['genre_classification'] = classify_spotify_playlist_with_genres(playlist_key,
                                                                                          update_in_db=False,
                                                                                          enriched_info=False)
            selected_playlists.append(curr_playlist)

    return selected_playlists


@router.get("/artists_by_name", status_code=HTTP_200_OK, tags=["spotify"])
def artists_by_names(names: str):
    regex_list = [re.compile(term, re.IGNORECASE) for term in names.split(',')]
    return find_many(settings.artists_collection_name, {'name': {'$in': regex_list}}, exclude_metadata=True)


@router.get("/playlist_genre_classification", status_code=HTTP_200_OK, tags=["spotify"])
def classify_genres_for_playlist(playlist_id: str):
    return classify_spotify_playlist_with_genres(playlist_id)


@router.get("/artists_for_genre", status_code=HTTP_200_OK, tags=["spotify"])
def get_artists_for_genre(genre: str):
    return find_artists_for_genre(genre)


@router.get("/genres", status_code=HTTP_200_OK, tags=["spotify"])
def genres():
    return find_all_genres()


@router.get("/tracks", status_code=HTTP_200_OK, tags=["spotify"])
def tracks():
    return find_all_tracks()


@router.get("/artists", status_code=HTTP_200_OK, tags=["spotify"])
def artists():
    return find_all_artists()


@router.get("/discover", status_code=HTTP_200_OK, tags=["spotify"])
def discover(genres: str, artists: str, tracks: str,
             limit: int = 20, market: str = None,
             min_popularity: int = None, max_popularity: int = None, target_popularity: int = None,
             min_tempo: int = None, max_tempo: int = None, target_tempo: int = None):
    # todo validate fields
    return discover_new_tracks(genres, artists, tracks, limit, market)


@router.post("/add_to_default_playlists", status_code=HTTP_200_OK, tags=["spotify"])
def add_to_playlist(playlist_index, track_id):
    return add_to_default_playlist(playlist_index, track_id)


@router.get("/exec_manual_script", status_code=HTTP_200_OK, tags=["spotify"])
def manual_exec():
    return exec_manual_script()
