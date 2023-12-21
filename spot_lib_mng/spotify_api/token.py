import datetime
import sys
import webbrowser
from base64 import b64encode
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from fastapi import HTTPException

from spot_lib_mng import database
from spot_lib_mng.config import settings

USERNAME = settings.spotify_username
HOST = settings.spotify_host
SCOPE = settings.spotify_scope

CLIENT_ID = settings.spotify_client_id
SECRET = settings.spotify_client_secret
REDIRECT_URI = settings.spotify_redirect_uri
ACCESS_TOKEN = settings.temp_access_token


def make_test_call(token: str) -> bool:
    url = f"https://api.spotify.com/v1/users/{USERNAME}/playlists"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return True
    return False


def get_access_token():
    auth_headers = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE
    }
    webbrowser.open("https://accounts.spotify.com/authorize?" + urlencode(auth_headers))


def evaluate_spotify_return_code(code: str):
    user_password = f"{CLIENT_ID}:{SECRET}"
    user_pass = b64encode(bytes(user_password, encoding='utf-8')).decode("ascii")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {user_pass}"
    }
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }
    response = requests.post(f"{HOST}/api/token", headers=headers, data=body)
    if response.status_code != 200:
        print(f"ERROR: response was not 200 - {response.status_code} - {response.text}")
        sys.exit(1)
    body = response.json()
    body['expiry_date'] = datetime.utcnow() + timedelta(0, body['expires_in'] - 5)

    print(f"SUCCESS: Generated access token for user '{USERNAME}.")
    return body


def get_valid_access_token():
    token = database.get_access_token()
    if not token:
        get_access_token()
        raise HTTPException(status_code=500,
                            detail="Token was not in DB. Will trigger auth process. Please try again in a moment.")
    if token and 'expiry_date' in token and datetime.utcnow() < token['expiry_date']:
        return token

    token = refresh_access_token(token['refresh_token'])
    return token


def refresh_access_token(refresh_token: str):
    print("INFO: Generating new token with refresh token...")
    user_password = f"{CLIENT_ID}:{SECRET}"
    user_pass = b64encode(bytes(user_password, encoding='utf-8')).decode("ascii")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {user_pass}"
    }
    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID
    }

    response = requests.post(f"{settings.spotify_host}/api/token", headers=headers, data=body)
    if response.status_code != 200:
        raise HTTPException(status_code=500,
                            detail="Could not refresh token. Please check with your admin.")
    token = response.json()
    database.store_access_token(token)
    return token
