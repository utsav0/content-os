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

@app.route("/posts")
def posts():
    return render_template("posts.html")

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
            
            # Fetch the main post
            cursor.execute("SELECT * FROM posts WHERE post_id = %s", (post_id,))
            post = cursor.fetchone()

            if not post:
                return "Post not found", 404

            if post and post.get('post_datetime'):
                post['post_datetime'] = post['post_datetime'].strftime('%d %B %Y')

            # Fetch topics for the current post
            cursor.execute("""
                SELECT t.id, t.name
                FROM topics t
                JOIN topic_posts tp ON t.id = tp.topic_id
                WHERE tp.post_id = %s
            """, (post_id,))
            topics = cursor.fetchall()

            # Fetch similar posts
            cursor.execute("""
                SELECT p.post_id, p.media_url, p.caption, p.impressions, p.likes, p.comments, p.reposts
                FROM posts p
                JOIN topic_posts tp ON p.post_id = tp.post_id
                WHERE tp.topic_id IN (
                    SELECT topic_id FROM topic_posts WHERE post_id = %s
                ) AND p.post_id != %s
                GROUP BY p.post_id
                ORDER BY p.post_datetime DESC
                LIMIT 10
            """, (post_id, post_id))
            similar_posts = cursor.fetchall()

            # Fetch the most recent post date among similar posts
            most_recent_post_info = None
            if similar_posts:
                cursor.execute("""
                    SELECT p.post_id, p.post_datetime
                    FROM posts p
                    JOIN topic_posts tp ON p.post_id = tp.post_id
                    WHERE tp.topic_id IN (
                        SELECT topic_id FROM topic_posts WHERE post_id = %s
                    )
                    ORDER BY p.post_datetime DESC
                    LIMIT 1
                """, (post_id,))
                most_recent_post_info = cursor.fetchone()
                if most_recent_post_info and most_recent_post_info.get('post_datetime'):
                    most_recent_post_info['post_datetime'] = most_recent_post_info['post_datetime'].strftime('%d %B %Y')

            return render_template('individual_post.html', post=post, topics=topics, similar_posts=similar_posts, most_recent_post_info=most_recent_post_info)

    except mysql.connector.Error as err:
        app.logger.error(f"Database error: {err}")
        return "Database error", 500
    

@app.route("/api/search-suggestions")
def search_suggestions():
    query = request.args.get("query", "")
    if not query:
        return jsonify({"topics": [], "posts": []})

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)

            # Search for topics
            cursor.execute("SELECT id, name FROM topics WHERE name LIKE %s", (f"%{query}%",))
            topics = cursor.fetchall()

            # Search for posts
            cursor.execute(
                "SELECT p.post_id, p.caption FROM posts p "
                "LEFT JOIN topic_posts tp ON p.post_id = tp.post_id "
                "LEFT JOIN topics t ON tp.topic_id = t.id "
                "WHERE p.caption LIKE %s OR t.name LIKE %s OR p.post_id LIKE %s",
                (f"%{query}%", f"%{query}%", f"%{query}%"),
            )
            posts = cursor.fetchall()
            
            topics_suggestions = [{"id": topic['id'], "name": topic['name']} for topic in topics]
            posts_suggestions = [{"post_id": str(post['post_id']), "caption": post['caption']} for post in posts]

            return jsonify({
                "topics": topics_suggestions,
                "posts": posts_suggestions
            })
    except mysql.connector.Error as err:
        app.logger.error(f"Database error: {err}")
        return jsonify({"error": "Database error"}), 500
    
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(debug=True)
