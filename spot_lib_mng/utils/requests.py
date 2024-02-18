import requests
from fastapi import HTTPException


def exec_get_request_with_headers_and_token_and_return_data(url: str, access_token: str):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 429:
        print(response.headers)
        raise HTTPException(status_code=429,
                            detail=f"Too many requests to spotify API. Retry again in: {int(response.headers['retry-after']) / 60} mins")
    elif response.status_code not in [200, 204]:
        print(
            f"ERROR - request to GET @ '{url}' was not successful. Response from external source: '{response.status_code}' - {response.text}")
        return {}
        # raise HTTPException(status_code=500, detail=f"Request to {url} was not successful. Error: {response.status_code} - {response.text}")

    return response.json()


def exec_post_request_with_headers_and_token(url: str, body: dict, access_token: str):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.post(url, json=body, headers=headers)
    if response.status_code not in [200, 201, 204]:
        print(f"ERROR: Request to POST @ '{url}' was not successful...")
        print(response.text)
        return {}

    return response.status_code


def exec_delete_request_with_headers_and_token(url: str, body: dict, access_token: str):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.delete(url, json=body, headers=headers)
    if response.status_code not in [200, 201, 204]:
        print(f"ERROR: Request to DELETE @ '{url}' was not successful...")
        print(response.text)
        return {}

    return response.status_code
