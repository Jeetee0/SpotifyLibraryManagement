from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    modifier: str

    spotify_username: str
    spotify_scope: str
    spotify_host: str

    spotify_playlist_url: str
    spotify_track_url: str
    spotify_artist_url: str
    spotify_top_user_artists_url: str
    spotify_top_user_tracks_url: str
    spotify_recommendations_url: str

    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str

    spotify_playlist_link_1: str
    spotify_playlist_link_2: str

    csv_playlist_ids_path: str
    diff_playlist_id: str

    mongodb_host: str
    mongodb_port: int
    mongodb_user: str
    mongodb_password: str
    db_name: str

    tracks_collection_name: str
    artists_collection_name: str
    playlist_collection_name: str
    diff_collection_name: str
    most_listened_collection_name: str
    token_collection_name: str

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
