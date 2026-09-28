import flask
import google_auth_oauthlib.flow
from google.oauth2 import id_token
from google.auth.transport import requests
from pathlib import Path

app = flask.Flask(__name__)
app.secret_key = "hihihaha"

CLIENT_SECRET_FILE = Path(__file__).with_name("client-secret.json")
SSL_CERTIFICATE = Path(__file__).with_name("localhost.pem")
SSL_KEY = Path(__file__).with_name("localhost-key.pem")

SCOPES = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid"
]

REDIRECT_URI = "https://localhost:5443/oauth2callback"


@app.route("/")
def login():
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
    )

    flow.redirect_uri = REDIRECT_URI

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account",
    )

    flask.session["state"] = state
    flask.session["code_verifier"] = flow.code_verifier

    return flask.redirect(authorization_url)

@app.route("/oauth2callback")
def oauth2callback():
    state = flask.session["state"]
    code_verifier = flask.session["code_verifier"]

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        state=state,
    )

    flow.redirect_uri = REDIRECT_URI
    flow.code_verifier = code_verifier

    flow.fetch_token(
        authorization_response=flask.request.url,
    )

    credentials = flow.credentials

    userInfo = id_token.verify_oauth2_token(
        credentials.id_token,
        requests.Request(),
        credentials.client_id,
    )

    googleUserId = userInfo["sub"]
    email = userInfo["email"]
    name = userInfo.get("name")
    picture = userInfo.get("picture")

    print("Google ID:", googleUserId)
    print("Email:", email)
    print("Name:", name)
    print("Picture:", picture)

    return {"success": True}
