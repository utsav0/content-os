from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import mysql.connector
from contextlib import contextmanager
import os
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler

# Load environment
load_dotenv()

# Flask app setup
app = Flask(__name__)
CORS(app)

# Logging
handler = RotatingFileHandler("app.log", maxBytes=100000, backupCount=3)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)

# Database config
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}

@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = mysql.connector.connect(**db_config)
        yield conn
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route("/")
def home():
    return render_template("home.html")
@app.route("/post-data")
def post_data():
    return render_template("index.html")

@app.route("/api/posts/ids")
def get_post_ids():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT post_id FROM posts")
            ids = [str(row[0]) for row in cursor.fetchall()]
            return jsonify(ids)
    except mysql.connector.Error as err:
        app.logger.error(f"Database error: {err}")
        return jsonify({"error": "Database error"}), 500

@app.route("/post/<int:post_id>")
def show_post_details(post_id):
    app.logger.info(f"Request received for post ID: {post_id}")
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM posts WHERE post_id = %s", (post_id,))
            post = cursor.fetchone()
            if post:
                return render_template("post_details.html", post=post)
            else:
                return "Post not found", 404
    except mysql.connector.Error as err:
        app.logger.error(f"Database error: {err}")
        return "Database error", 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(debug=True)
