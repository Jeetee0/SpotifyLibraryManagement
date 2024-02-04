#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# API for Spotify Library Management

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from spot_lib_mng.config import settings
from spot_lib_mng import spotify_routers

app = FastAPI(title="Spotify Library Management Service",
               version="1.0.0",
               description=f"This is the API Documentation for the Spotify Library Management Service. Current used user is '{settings.spotify_username}'",
               )

origins = [
    "http://localhost",
    "http://localhost:5173",
    "https://jeetee0.github.io"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=['Access-Control-Allow-Origin']
)

app.include_router(spotify_routers.router, prefix="/spotify")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9090, log_level="debug", reload=True)
