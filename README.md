# vod_auto_upload
Automatically upload Twitch VODs to YouTube

## Prerequisites
1. A project in the [Google Developer Console](https://console.developers.google.com)
    * Under credentials, create a new OAuth Client ID
    * With the project selected, search for `YouTube Data API` (or click [here](https://console.developers.google.com/apis/library/youtube.googleapis.com)) and enable it

2. A project in the [Twitch Developer Console](https://dev.twitch.tv/console)

## Usage
1. Install the dependencies
    * `pip install requests requests_oauthlib pytz`

2. Run `src/bot.py` once so `data/config.json` can be generated

3. Update `data/config.json` with your credentials and corrected file paths

4. Use `bot.py --match-vods-only` to see which files are detected (nothing will be uploaded)

### Arguments
`bot.py` supports the following arguments:
- `--match-vods-only`: Print which videos will be uploaded
- `--dry-run`: Do everything except for actually uploading the videos
- `--no-size-age`: Ignore video file size and last modified time

## Config
For config options documentation, check out the [Wiki Page](https://github.com/afrmtbl/vod_auto_upload/wiki/Config-Documentation)
