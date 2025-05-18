import os
import secrets
from flask import Flask, request, redirect, session, render_template_string
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

def db_conn():
    return connect(os.getenv("DATABASE_URL"), cursor_factory=RealDictCursor)

@app.route("/verify")
def verify():
    token = request.args.get("token")
    if not token:
        return "Invalid token."

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM links WHERE token = %s AND verified = FALSE", (token,))
            user_row = cur.fetchone()
            if not user_row:
                return "Invalid or expired token."

    session["token"] = token
    mw = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET, callback_uri=CALLBACK_URL)
    fetch_response = mw.fetch_request_token(f"{MW_API_URL}?action=initiateoauth&format=json")

    session["oauth_token"] = fetch_response.get("oauth_token")
    session["oauth_token_secret"] = fetch_response.get("oauth_token_secret")

    authorization_url = mw.authorization_url(f"{MW_API_URL}?action=authorizeoauth")
    return redirect(authorization_url)

@app.route("/verify/callback")
def callback():
    token = session.get("token")
    oauth_token = request.args.get("oauth_token")
    verifier = request.args.get("oauth_verifier")

    if not token or not oauth_token or not verifier:
        return "Invalid session."

    mw = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=session["oauth_token"],
        resource_owner_secret=session["oauth_token_secret"],
        verifier=verifier,
    )

    mw_tokens = mw.fetch_access_token(f"{MW_API_URL}?action=completeoauth&format=json")
    mw = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=mw_tokens["oauth_token"],
        resource_owner_secret=mw_tokens["oauth_token_secret"]
    )

    identity = mw.get(f"{MW_API_URL}?action=query&meta=userinfo&format=json").json()
    username = identity["query"]["userinfo"]["name"]

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE links SET verified = TRUE, mediawiki_username = %s WHERE token = %s", (username, token))
            conn.commit()

    return render_template_string("""
    <html>
        <head><title>Verification Complete</title></head>
        <body>
            <h2>Verification Complete</h2>
            <p>Welcome, {{ username }}. You have linked your account.</p>
        </body>
    </html>
    """, username=username)
