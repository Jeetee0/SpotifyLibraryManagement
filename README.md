# SpotifyLibraryManagement
To backup your spotify playlist and user data state

You will need a local mongodb running with default settings to store the current state. 

Create a '.env' file from template and copy missing values:
* SPOTIFY_USERNAME
* SPOTIFY_CLIENT_ID
* SPOTIFY_CLIENT_SECRET
* DIFF_PLAYLIST_ID (spotify playlist id, where to insert newest tracks)

You will also need a csv file 'spotify_playlist_ids.csv' where your playlists should be defined which you want to export the state from. Use this header which defines the format:
```
name;folder;id;
```
