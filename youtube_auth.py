import os
import json
import time
import math
import webbrowser
from requests_oauthlib import OAuth2Session

from redirect_server import wait_for_auth_redirection

from config import config

def token_saver(auth_data):
    with open("auth.json", "w") as auth_file:
        auth_file.write(json.dumps(auth_data, indent=4))

def after_server_start(authorization_url):
    print("The authorization url should have opened in your default browser. If it hasn\'t, please go here to authorize:", authorization_url)
    webbrowser.open(authorization_url)

# Credentials you get from registering a new application
# client_id = "687701237754-cmhbj9toli2h5nhfirm2u9igeafuittn.apps.googleusercontent.com"
# client_secret = "-oPHEIWqGP9FLdxpomeyMcN6"

client_id = config["youtube_client_id"]
client_secret = config["youtube_client_secret"]

redirect_host = config["redirect_host"] + str(config["redirect_port"])
redirect_uri = f"http://{redirect_host}/submit_credentials"

# OAuth endpoints given in the Google API documentation
authorization_base_url = "https://accounts.google.com/o/oauth2/v2/auth"
token_url = "https://www.googleapis.com/oauth2/v4/token"
scope = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/youtube.upload"
]

def test_auth(google_session):
     # Fetch a protected resource, i.e. user profile
    r = google_session.get("https://www.googleapis.com/oauth2/v1/userinfo")
    print(json.dumps(json.loads(r.text), indent=4))

def init_google_session():
    if os.path.isfile("auth.json"):

        with open("auth.json", "r+", encoding="utf-8") as auth_file:
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

        # offline for refresh token
        # force to always make user click authorize
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

            print("Authorization was granted. Fetching auth tokens...")

            # Fetch the access token (and other related data)
            auth_data = google.fetch_token(
                token_url, 
                client_secret=client_secret,
                authorization_response=redirect_response
            )

            print("Received auth tokens")
            token_saver(auth_data)

            return google
        else:
            print("Authorization must be provided in order to upload videos on your behalf")
            return None


def main():

    google = init_google_session()

    if google:
        test_auth(google)
    else:
        print("Unable to get initialize a Google session")


if __name__ == '__main__':
    main()