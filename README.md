# vod_auto_upload
Automatically upload Twitch VODs to YouTube

## Installing Dependencies
`pip install requests requests_oauthlib pytz`

## Config
`folder_to_watch`: The folder where the local recordings are located

`folder_to_move_completed_videos`: The folder where recordings that are successfully uploaded will be moved

`check_folder_interval`: How often `folder_to_watch` will be checked for new recordings (in seconds)

`file_size_threshold`: The minimum file size (in bytes) a recording must be before it is considered for uploading

`file_age_threshold`: The amount of time (in seconds) that must have passed since the last time the file was modified

`file_chunk_size_override`: Used for setting a custom upload chunk size. Either the amount of bytes per chunk, or `false` for automatic

`twitch_video_duration_threshold`: The minimum length a matching Twitch VOD must be (in seconds)

`file_modified_start_max_delta`: The amount of seconds ahead of the Twitch VOD that the recording is allowed to have started

`file_modified_end_max_delta`: The amount of seconds after the Twitch VOD that the recording is allowed to have ended

`youtube_client_id`: OAuth 2.0 Client ID used for requesting access to upload YouTube videos on an authorized YouTube account. Can be created/found at the [Google Developer Console](https://console.developers.google.com/)

`youtube_client_secret`: OAuth 2.0 Client Secret

`twitch_client_id`: Twitch application client ID used for retrieving a list of VODs. Can be created/found at the [Twitch Developer Console](https://dev.twitch.tv/console/apps)

`twitch_user_id`: The Twitch user ID of the channel that contains the VODs that local recordings will be checked against

`twitch_vod_refresh_rate`: How often (in seconds) twitch vod information should be fetched. Will happen with the check folder interval
