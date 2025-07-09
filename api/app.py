import os
import logging
import datetime
from typing import Dict, Any
import jwt
from markupsafe import escape
from flask import (
    Flask,
    request,
    redirect,
    abort,
    render_template_string,
    session,
)
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv
from psycopg2 import connect
from psycopg2.extras import RealDictCursor

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

CONSUMER_KEY = os.getenv("MW_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("MW_CONSUMER_SECRET")
MW_API_URL = os.getenv("MW_API_URL")
CALLBACK_URL = os.getenv("CALLBACK_URL")
BASE_URL = os.getenv("MW_BASE_URL")

JWT_SECRET = os.getenv("JWT_SECRET", app.secret_key)
assert JWT_SECRET is not None  # JWT_SECRET must be set
JWT_ALGORITHM = "HS256"
JWT_EXP_DELTA_SECONDS = 600  # 10 minutes

DARK_MODE_TEMPLATE = """
<html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{{ title }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                background: #181a1b;
                color: #e8e6e3;
                font-family: 'Segoe UI', 'Arial', sans-serif;
                margin: 0;
                padding: 0;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .container {
                background: #23272a;
                border-radius: 12px;
                box-shadow: 0 4px 24px rgba(0,0,0,0.5);
                padding: 2.5rem 2rem;
                max-width: 400px;
                width: 100%;
                text-align: center;
            }
            h2 {
                margin-top: 0;
                color: #8ec07c;
                font-weight: 600;
            }
            p {
                color: #e8e6e3;
                margin-bottom: 0;
            }
            @media (max-width: 500px) {
                .container {
                    padding: 1.5rem 0.5rem;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>{{ title }}</h2>
            <p>{{ message|safe }}</p>
        </div>
    </body>
</html>
"""

if not all(
    [
        CONSUMER_KEY,
        CONSUMER_SECRET,
        MW_API_URL,
        CALLBACK_URL,
        app.secret_key,
        JWT_SECRET,
    ]
):
    raise RuntimeError("One or more required environment variables are missing.")

assert JWT_SECRET is not None  # For type checker

assert MW_API_URL is not None  # For type checker

request_token_url = f"{BASE_URL}/Special:OAuth/initiate"
access_token_url = f"{BASE_URL}/Special:OAuth/token"
authorize_url = f"{BASE_URL}/Special:OAuth/authorize"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.debug(f"Using CONSUMER_KEY: {CONSUMER_KEY}")


def db_conn():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable missing")
    return connect(db_url, cursor_factory=RealDictCursor)


def create_jwt(payload: Dict[str, Any]) -> str:
    payload_copy = payload.copy()
    payload_copy["exp"] = datetime.datetime.now(
        datetime.timezone.utc
    ) + datetime.timedelta(seconds=JWT_EXP_DELTA_SECONDS)
    # Type cast to satisfy type checker - JWT_SECRET is validated at startup
    token = jwt.encode(payload_copy, str(JWT_SECRET), algorithm=JWT_ALGORITHM)
    return token if isinstance(token, str) else token.decode("utf-8")


def decode_jwt(token: str) -> Dict[str, Any]:
    try:
        # Type cast to satisfy type checker - JWT_SECRET is validated at startup
        return jwt.decode(token, str(JWT_SECRET), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        abort(
            400,
            "Verification link has expired. Please restart the verification process.",
        )
    except jwt.InvalidTokenError:
        abort(
            400, "Invalid verification token. Please restart the verification process."
        )


def error_page(title: str, message: str):
    contact_html = (
        '<br><br>'
        'Please report this error to atl.wiki staff '
        '(<a href="https://atl.wiki/Atl.wiki:Contact" target="_blank" rel="noopener noreferrer">contact</a>).'
    )
    return render_template_string(
        DARK_MODE_TEMPLATE,
        title=escape(title),
        message=escape(message).replace('\n', '<br>') + contact_html
    )


@app.route("/verify")
def verify():
    try:
        token = request.args.get("token")
        if not token:
            return error_page(
                "Missing Token", "Verification token is missing from the request."
            )

        oauth = OAuth1Session(
            CONSUMER_KEY, client_secret=CONSUMER_SECRET, callback_uri="oob"
        )
        fetch_response = oauth.fetch_request_token(request_token_url)  # type: ignore[misc]

        resource_owner_key = fetch_response.get("oauth_token")
        resource_owner_secret = fetch_response.get("oauth_token_secret")

        if not resource_owner_key or not resource_owner_secret:
            raise ValueError("Missing tokens in fetch response")

        # Store secret and token in session for later retrieval
        session["request_token_secret"] = resource_owner_secret
        session["token"] = token
        session["request_token_key"] = resource_owner_key

        # Create callback URL (no extra params)
        callback_url = CALLBACK_URL

        oauth = OAuth1Session(
            CONSUMER_KEY,
            client_secret=CONSUMER_SECRET,
            resource_owner_key=resource_owner_key,
            resource_owner_secret=resource_owner_secret,
            callback_uri=callback_url,
        )
        try:
            authorization_url = oauth.authorization_url(authorize_url)  # type: ignore[misc]
        except Exception as e:
            logging.exception("Failed to generate authorization URL")
            return error_page(
                "OAuth Error", f"Failed to generate authorization URL: {e}"
            )
        return redirect(authorization_url)

    except Exception as e:
        logging.exception("Error during /verify")
        return f"OAuth error during request token fetch: {e}", 500


@app.route("/verify/callback")
def callback():
    oauth_token = request.args.get("oauth_token")
    verifier = request.args.get("oauth_verifier")

    if not oauth_token or not verifier:
        return error_page("OAuth Verification Failed", "Missing OAuth parameters.")

    stored_token_key = session.get("request_token_key")
    stored_token_secret = session.get("request_token_secret")
    token = session.get("token")

    if not stored_token_key or not stored_token_secret or not token:
        return error_page(
            "OAuth Verification Failed",
            "Session expired or missing data. Please restart verification.",
        )

    if oauth_token != stored_token_key:
        return error_page(
            "OAuth Verification Failed", "OAuth token mismatch. Try again."
        )

    try:
        oauth = OAuth1Session(
            CONSUMER_KEY,
            client_secret=CONSUMER_SECRET,
            resource_owner_key=stored_token_key,
            resource_owner_secret=stored_token_secret,
            verifier=verifier,
        )
        access_token_response = oauth.fetch_access_token(access_token_url)  # type: ignore[misc]
    except Exception as e:
        logging.exception("OAuth token exchange failed")
        return error_page("OAuth Token Exchange Failed", str(e))

    try:
        oauth = OAuth1Session(
            CONSUMER_KEY,
            client_secret=CONSUMER_SECRET,
            resource_owner_key=access_token_response.get("oauth_token"),
            resource_owner_secret=access_token_response.get("oauth_token_secret"),
        )
        identity_response = oauth.get(
            f"{MW_API_URL}?action=query&meta=userinfo&format=json"
        ).json()
        logging.debug(f"IDENTITY RESPONSE : {identity_response}")
        username = identity_response["query"]["userinfo"]["name"]
    except Exception as e:
        logging.exception("Failed to fetch user info")
        return error_page("Failed to Fetch User Info", str(e))

    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE links SET verified = TRUE, mediawiki_username = %s WHERE token = %s",
                    (username, token),
                )
                conn.commit()
    except Exception as e:
        logging.exception("Database update failed")
        return error_page("Database Update Failed", str(e))

    return render_template_string(
        DARK_MODE_TEMPLATE,
        title="Verification Complete",
        message=f"Welcome, {escape(username)}.<br>You have linked your account successfully.<br><br>You may close this tab."
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)
