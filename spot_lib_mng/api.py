#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# API for Spotify Library Management

from fastapi import FastAPI
from spot_lib_mng.config import settings
from spot_lib_mng import spotify_routers
from spot_lib_mng.spotify_api.token import get_access_token

app = FastAPI(title="Spotify Library Management Service",
               version="1.0.0",
               description=f"This is the API Documentation for the Spotify Library Management Service. Current used user is '{settings.spotify_username}'",
               )

app.include_router(spotify_routers.router, prefix="/spotify")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9090, log_level="debug", reload=True)
