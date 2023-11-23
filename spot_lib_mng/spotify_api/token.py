import os
import webbrowser
from base64 import b64encode
from urllib.parse import urlencode

from spot_lib_mng.config import settings
import requests

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
        import sys
        sys.exit(1)
    body = response.json()
    access_token = body['access_token']
    print(f"SUCCESS: Generated access token for user '{USERNAME}.")
    os.environ["TEMP_ACCESS_TOKEN"] = access_token
    return access_token