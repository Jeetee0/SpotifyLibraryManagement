import json
import os
import time

from fastapi import APIRouter
from starlette.status import HTTP_200_OK, HTTP_201_CREATED
from bson.json_util import dumps

from spot_lib_mng.config import settings
from spot_lib_mng.database import store_access_token
from spot_lib_mng.database import find_latest_documents
from spot_lib_mng.spotify_api.token import get_access_token, evaluate_spotify_return_code
from spot_lib_mng.spotify_api.user_data import retrieve_spotify_user_data, get_current_state_of_spotify_playlists, \
    create_diff_between_latest_playlist_states

router = APIRouter()


@router.get("/trigger_complete_data_retrieval", status_code=HTTP_200_OK, tags=["spotify"])
def request_access_token():
    get_access_token()


@router.get("/retrieve_code", status_code=HTTP_200_OK, tags=["spotify"])
def retrieve_code(code: str):
    token = evaluate_spotify_return_code(code)
    store_access_token(token)
    retrieve_spotify_user_data()
    playlists_count, tracks_count = get_current_state_of_spotify_playlists()
    create_diff_between_latest_playlist_states()
    return {"status": "success", 'amount_of_playlists': playlists_count, 'total_amount_of_tracks_in_playlists': tracks_count}


@router.get("/latest_playlist_states", status_code=HTTP_200_OK, tags=["spotify"])
def latest_playlist_states(amount: int = 3):
    return json.loads(dumps(find_latest_documents(settings.playlist_collection_name, amount)))


@router.get("/latest_diff_states", status_code=HTTP_200_OK, tags=["spotify"])
def latest_playlist_states(amount: int = 3):
    return json.loads(dumps(find_latest_documents(settings.diff_collection_name, amount)))


@router.get("/latest_user_data_states", status_code=HTTP_200_OK, tags=["spotify"])
def latest_playlist_states(amount: int = 3):
    return json.loads(dumps(find_latest_documents(settings.most_listened_collection_name, amount)))


# @router.get("/user_data", status_code=HTTP_200_OK, tags=["spotify"])
# def read_spotify_user_data():
#     return retrieve_spotify_user_data()
#
#
# @router.get("/user_playlists", status_code=HTTP_200_OK, tags=["spotify"])
# def read_spotify_user_playlists():
#     playlists_count, tracks_count = get_current_state_of_spotify_playlists()
#     return {'amount_of_playlists': playlists_count, 'total_amount_of_tracks_in_playlists': tracks_count}
#
#
# @router.get("/create_diff", status_code=HTTP_201_CREATED, tags=["spotify"])
# def create_diff_from_latest_playlist_state():
#     create_diff_between_latest_playlist_states()

