"""
Handles retrieving and saving OAuth credentials used to initialize an
authenticated Requests Session for calling the YouTube Data API.
"""

import os
import json
import time
import math
import webbrowser
from requests_oauthlib import OAuth2Session

from redirect_server import start_server, wait_for_auth_redirection

from config import config

import logging
logger = logging.getLogger()

ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/.."))
AUTH_FILE_PATH = ROOT_DIR + "/data/auth.json"

if not config["youtube_client_id"] or not config["youtube_client_secret"]:
    print("Please enter your YouTube Client ID and YouTube Client Secret in data/config.json. (More info in the README)")
    exit(1)


def token_saver(auth_data):
    """Writes the OAuth token (and related data) to AUTH_FILE_PATH."""
    with open(AUTH_FILE_PATH, "w") as auth_file:
        auth_file.write(json.dumps(auth_data, indent=4))


def after_server_start(authorization_url):
    """Executed by redirect_server.py after the server is started."""
    print("The authorization url should have opened in your default browser. If it hasn\'t, please go here to authorize:", authorization_url)
    webbrowser.open(authorization_url)


client_id = config["youtube_client_id"]
client_secret = config["youtube_client_secret"]

# OAuth endpoints given in the Google API documentation
authorization_base_url = "https://accounts.google.com/o/oauth2/v2/auth"
token_url = "https://www.googleapis.com/oauth2/v4/token"
scope = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/youtube.upload"
]


def test_auth(google_session: dict):
    """
    Fetches a protected resource, i.e. user profile.
    Used for testing OAuth credentials.
    """
    r = google_session.get("https://www.googleapis.com/oauth2/v1/userinfo")
    print(json.dumps(json.loads(r.text), indent=4))


def init_google_session():
    """Initializes a Requests Session with the proper headers for calling Google APIs requiring OAuth (YouTube in this case)"""

    # A server is started even when we already have credentials saved from an earlier run
    # in case the token needs to be refreshed.
    server_addr = start_server()

    redirect_host = server_addr[0] + ":" + str(server_addr[1])
    redirect_uri = f"http://{redirect_host}/submit_credentials"

    if os.path.isfile(AUTH_FILE_PATH):

        with open(AUTH_FILE_PATH, "r+", encoding="utf-8") as auth_file:
            auth_data = json.loads(auth_file.read())

            # update the "expires_in" key
            auth_data["expires_in"] = math.floor(auth_data["expires_at"] - time.time())

            auth_file.truncate(0)
            auth_file.seek(0)

            auth_file.write(json.dumps(auth_data, indent=4))

        google = OAuth2Session(
            client_id,
            scope=scope,
            token=auth_data,
            redirect_uri=redirect_uri,
            auto_refresh_url=token_url,
            auto_refresh_kwargs={"client_id": client_id, "client_secret": client_secret},
            token_updater=token_saver
        )

        return google

    else:

        google = OAuth2Session(
            client_id,
            scope=scope,
            redirect_uri=redirect_uri,
            auto_refresh_url=token_url,
            auto_refresh_kwargs={"client_id": client_id, "client_secret": client_secret},
            token_updater=token_saver
        )

        # Offline for refresh token
        # Force to always make user click authorize
        authorization_url, state = google.authorization_url(
            authorization_base_url,
            access_type="offline",
            prompt="select_account"
        )
        redirect_response = None

        def redirect_callback(handler, request_path):
            nonlocal redirect_response
            if request_path:
                full_url = f"https://{redirect_host}/{request_path}"
                redirect_response = full_url

        # Get the authorization verifier code from the callback url
        wait_for_auth_redirection(state, redirect_callback, after_server_start, authorization_url)

        if redirect_response:

            logger.info("Authorization was granted. Fetching auth tokens...")

            # Fetch the access token (and other related data)
            auth_data = google.fetch_token(
                token_url,
                client_secret=client_secret,
                authorization_response=redirect_response
            )

            logger.info("Received auth tokens")
            token_saver(auth_data)

            return google
        else:
            logger.error("Authorization must be provided in order to upload videos on your behalf")
            return None


def main():

    google = init_google_session()

    if google:
        test_auth(google)
    else:
        print("Unable to get initialize a Google session")


if __name__ == '__main__':
    main()
