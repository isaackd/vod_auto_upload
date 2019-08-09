"""Simple server to receive the authorization code from Google after the user is redirected."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import time

import logging

logger = logging.getLogger()

host_name = "localhost"
host_port = 0

server_should_stop = False
my_server = None


class MyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global server_should_stop

        query_part = self.path.split("?")
        query_params = {}

        if len(query_part) >= 2:
            qp_pairs = query_part[1].split("&")
            for key, value in (pair.split("=") for pair in qp_pairs):
                query_params[key] = value
        else:
            return

        request_state = query_params["state"]

        if "error" in query_params:
            self.send_response(400)
            self.wfile.write(f"Authorization must be provided in order to upload videos on your behalf".encode("utf-8"))
            self.received_callback(None)
            server_should_stop = True
        elif self.path.startswith("/submit_credentials") and self.state_code == request_state:
            self.send_response(200)
            self.wfile.write(f"Received access token. This window can now be closed".encode("utf-8"))
            self.received_callback(self.path)
            server_should_stop = True
        else:
            self.send_response(400)
            self.wfile.write(f"Bad Request".encode("utf-8"))

    def log_message(self, format, *args):
        return


def start_server():
    global my_server
    my_server = HTTPServer((host_name, host_port), MyHandler)
    return my_server.server_address


def wait_for_auth_redirection(state_code, callback, after_server_start, *args):
    global my_server
    logger.debug(f"{time.asctime()} Server Start - {my_server.server_address}")

    after_server_start(*args)

    my_server.RequestHandlerClass.received_callback = callback
    my_server.RequestHandlerClass.state_code = state_code

    while not server_should_stop:
        my_server.handle_request()

    my_server.server_close()
    logger.debug(f"{time.asctime()} Server Stop - {my_server.server_address}")


if __name__ == '__main__':
    start_server()
    wait_for_auth_redirection(None, None, None)
