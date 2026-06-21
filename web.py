import sqlite3
from urllib.parse import quote

import requests
from flask import Flask, render_template, request

from setting import (
    DATABASE_PATH,
    DISCORD_BOT_TOKEN,
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    FLASK_SECRET_KEY,
    OAUTH_REDIRECT_URI,
    WEB_HOST,
    WEB_PORT,
    api_endpoint,
)


app = Flask(__name__, template_folder="templates")
app.secret_key = FLASK_SECRET_KEY


def start_db():
    con = sqlite3.connect(DATABASE_PATH)
    cur = con.cursor()
    return con, cur


def init_db():
    con, cur = start_db()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS guilds (
            id INTEGER,
            token TEXT,
            expiredate TEXT,
            link TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER,
            token TEXT,
            guild_id INTEGER
        )
        """
    )
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_guilds_id ON guilds(id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_id_guild ON users(id, guild_id)")
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_guilds_link
        ON guilds(link)
        WHERE link IS NOT NULL AND link != ''
        """
    )
    con.commit()
    con.close()


def bot_headers():
    return {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}


def get_user_profile(access_token):
    response = requests.get(
        f"{api_endpoint}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if response.status_code != 200:
        return None
    return response.json()


def getguild(guild_id):
    response = requests.get(
        f"{api_endpoint}/guilds/{guild_id}",
        headers=bot_headers(),
        timeout=15,
    )
    if response.status_code != 200:
        return None
    return response.json()


def get_guild_counts(guild_id):
    response = requests.get(
        f"{api_endpoint}/guilds/{guild_id}?with_counts=true",
        headers=bot_headers(),
        timeout=15,
    )
    if response.status_code != 200:
        return {}
    return response.json()


def add_user(access_token, user_id, guild_id):
    response = requests.put(
        f"{api_endpoint}/guilds/{guild_id}/members/{user_id}",
        json={"access_token": access_token},
        headers=bot_headers(),
        timeout=15,
    )
    return response.status_code in (201, 204)


def exchange_code(code):
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": OAUTH_REDIRECT_URI,
    }
    response = requests.post(
        f"{api_endpoint}/oauth2/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    if response.status_code != 200:
        return None
    return response.json()


def build_auth_url(guild_id):
    redirect_uri = quote(OAUTH_REDIRECT_URI, safe="")
    scope = quote("identify guilds.join", safe="")
    return (
        "https://discord.com/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        f"&scope={scope}"
        f"&state={guild_id}"
    )


@app.route("/<link>", methods=["GET"])
def join_page(link):
    con, cur = start_db()
    cur.execute("SELECT id FROM guilds WHERE link == ?;", (link,))
    row = cur.fetchone()
    con.close()

    if row is None:
        return render_template("fail.html"), 404

    guild_id = row[0]
    guild_info = getguild(guild_id)
    if guild_info is None:
        return render_template("fail.html"), 502

    counts = get_guild_counts(guild_id)
    icon = guild_info.get("icon")
    icon_url = None
    if icon:
        icon_url = f"https://cdn.discordapp.com/icons/{guild_id}/{icon}.png"

    return render_template(
        "s.html",
        link=link,
        guild_id=guild_id,
        guild_name=guild_info.get("name", "Discord Server"),
        icon_url=icon_url,
        member_count=counts.get("approximate_member_count"),
        auth_url=build_auth_url(guild_id),
    )


@app.route("/join", methods=["GET"])
def callback():
    code = request.args.get("code")
    state = request.args.get("state")

    if not code or not state or not state.isdigit():
        return render_template("fail.html"), 400

    con, cur = start_db()
    cur.execute("SELECT id FROM guilds WHERE id == ?;", (int(state),))
    guild_row = cur.fetchone()
    con.close()
    if guild_row is None:
        return render_template("fail.html"), 404

    token_result = exchange_code(code)
    if not token_result or "access_token" not in token_result or "refresh_token" not in token_result:
        return render_template("fail.html"), 400

    user = get_user_profile(token_result["access_token"])
    if user is None:
        return render_template("fail.html"), 400

    add_user(token_result["access_token"], user["id"], int(state))

    con, cur = start_db()
    cur.execute(
        """
        INSERT INTO users(id, token, guild_id)
        VALUES(?, ?, ?)
        ON CONFLICT(id, guild_id) DO UPDATE SET token = excluded.token
        """,
        (int(user["id"]), token_result["refresh_token"], int(state)),
    )
    con.commit()
    con.close()

    return render_template("success.html")


if __name__ == "__main__":
    init_db()
    app.run(debug=False, host=WEB_HOST, port=WEB_PORT)
