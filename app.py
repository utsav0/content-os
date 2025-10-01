from flask import Flask, jsonify, render_template, request, redirect, url_for, session
from flask_cors import CORS
import mysql.connector
from contextlib import contextmanager
import os
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
import statistics
import file_handler
import sys
import json

# Load environment
load_dotenv()

# Flask app setup
app = Flask(__name__)
CORS(app)

# For session storage
app.secret_key = os.getenv("SECRET_KEY")

# Logging
logging.basicConfig(level=logging.INFO, handlers=[
    RotatingFileHandler("app.log", maxBytes=100000, backupCount=3),
    logging.StreamHandler(sys.stdout)
])

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

@app.route("/add-post", methods=['GET', 'POST'])
def add_post():
    error = None
    if request.method == 'POST':
        files = request.files.getlist('file-upload')
        if not files or not files[0].filename:
            error = "No file selected."
        else:
            result = file_handler.handle_files(files)
            if isinstance(result, dict): 
                session['last_upload'] = result 
                return redirect(url_for('confirm_upload_post'))
            else:
                error = result 
    return render_template("add_post.html", error=error)

@app.route("/confirm-upload-post")
def confirm_upload_post():
    data = session.get('last_upload')
    if not data:
        return redirect(url_for('add_post'))
    return render_template("confirm_upload_post.html", data=data)

@app.route("/posts")
def posts():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT post_id, caption, impressions, likes, comments, post_datetime FROM posts ORDER BY post_datetime DESC LIMIT 20")
            initial_posts = cursor.fetchall()
            for post in initial_posts:
                if post.get('post_datetime'):
                    post['post_datetime'] = post['post_datetime'].strftime('%d %B %Y')
            return render_template("posts.html", posts=initial_posts)
    except mysql.connector.Error as err:
        app.logger.error(f"Database error: {err}")
        return "Database error", 500
    
@app.route("/api/posts")
def api_posts():
    try:
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 20))
        sort_by = request.args.get("sort_by", "post_datetime")
        sort_order = request.args.get("sort_order", "desc").upper()
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        likes_min = request.args.get("likes_min")
        likes_max = request.args.get("likes_max")
        impressions_min = request.args.get("impressions_min")
        impressions_max = request.args.get("impressions_max")
        comments_min = request.args.get("comments_min")
        comments_max = request.args.get("comments_max")

        # Whitelist to prevent injection
        valid_sort_columns = ["post_datetime", "likes", "comments", "impressions"]
        if sort_by not in valid_sort_columns:
            sort_by = "post_datetime"
        if sort_order not in ["ASC", "DESC"]:
            sort_order = "DESC"

        query = """SELECT post_id, caption, impressions, likes, comments, post_datetime
                   FROM posts WHERE 1=1"""
        params = []

        if date_from:
            query += " AND post_datetime >= %s"
            params.append(date_from)
        if date_to:
            query += " AND post_datetime <= %s"
            params.append(date_to)
        if likes_min:
            query += " AND likes >= %s"
            params.append(likes_min)
        if likes_max:
            query += " AND likes <= %s"
            params.append(likes_max)
        if impressions_min:
            query += " AND impressions >= %s"
            params.append(impressions_min)
        if impressions_max:
            query += " AND impressions <= %s"
            params.append(impressions_max)
        if comments_min:
            query += " AND comments >= %s"
            params.append(comments_min)
        if comments_max:
            query += " AND comments <= %s"
            params.append(comments_max)

        query += f" ORDER BY {sort_by} {sort_order} LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params)
            posts = cursor.fetchall()

            for post in posts:
                if "post_id" in post and post["post_id"] is not None:
                    post["post_id"] = str(post["post_id"])

                if post.get("post_datetime"):
                    post["post_datetime"] = post["post_datetime"].strftime("%d %B %Y")

            return jsonify(posts)

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


@app.route("/topic/<int:topic_id>")
def show_topic_details(topic_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)

            # Fetch topic details
            cursor.execute("SELECT * FROM topics WHERE id = %s", (topic_id,))
            topic = cursor.fetchone()

            if not topic:
                return "Topic not found", 404

            # Fetch all posts for this topic
            cursor.execute("""
                SELECT p.*
                FROM posts p
                JOIN topic_posts tp ON p.post_id = tp.post_id
                WHERE tp.topic_id = %s
                ORDER BY p.post_datetime DESC
            """, (topic_id,))
            posts = cursor.fetchall()

            # Fetch relevant topics
            cursor.execute("""
                SELECT t.id, t.name, COUNT(t.id) as post_count
                FROM topics t
                JOIN topic_posts tp ON t.id = tp.topic_id
                WHERE tp.post_id IN (
                    SELECT post_id FROM topic_posts WHERE topic_id = %s
                ) AND t.id != %s
                GROUP BY t.id, t.name
                ORDER BY post_count DESC
                LIMIT 10
            """, (topic_id, topic_id))
            relevant_topics = cursor.fetchall()

            total_posts = len(posts)
            last_post_date = ""
            if posts:
                last_post_date = posts[0]['post_datetime'].strftime('%d %B %Y')

            # Calculate stats
            likes = [p['likes'] for p in posts if p['likes'] is not None]
            impressions = [p['impressions'] for p in posts if p['impressions'] is not None]
            comments = [p['comments'] for p in posts if p['comments'] is not None]

            stats = {
                'avg_likes': statistics.mean(likes) if likes else 0,
                'median_likes': statistics.median(likes) if likes else 0,
                'avg_impressions': statistics.mean(impressions) if impressions else 0,
                'median_impressions': statistics.median(impressions) if impressions else 0,
                'avg_comments': statistics.mean(comments) if comments else 0,
                'median_comments': statistics.median(comments) if comments else 0,
            }

            return render_template('topic.html',
                                   topic=topic,
                                   posts=posts,
                                   total_posts=total_posts,
                                   last_post_date=last_post_date,
                                   stats=stats,
                                   relevant_topics=relevant_topics)

    except mysql.connector.Error as err:
        app.logger.error(f"Database error in topic details: {err}")
        return "Database error", 500
    

@app.route("/api/topics")
def api_topics():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, name FROM topics")
            topics = cursor.fetchall()
            return jsonify(topics)
    except mysql.connector.Error as err:
        app.logger.error(f"Database error: {err}")
        return jsonify({"error": "Database error"}), 500


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

@app.route("/api/save-post", methods=['POST'])
def save_post():
    data = request.get_json()
    post_data = data.get('post_data')
    tags = data.get('tags')

    if not post_data or not tags:
        return jsonify({"error": "Missing data"}), 400

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            conn.start_transaction()

            try:
                # Prepare post data
                post_columns = [key for key in post_data.keys() if key != 'media_url']
                post_values = [post_data[key] for key in post_columns]
                
                # Handle media_url separately
                if 'media_url' in post_data and post_data['media_url']:
                    post_columns.append('media_url')
                    post_values.append(post_data['media_url'])

                query = f"INSERT INTO posts ({', '.join(post_columns)}) VALUES ({', '.join(['%s'] * len(post_columns))})"
                cursor.execute(query, post_values)
                post_id = post_data['post_id']

                # Handle topics
                topic_ids = []
                for tag in tags:
                    cursor.execute("SELECT id FROM topics WHERE name = %s", (tag,))
                    result = cursor.fetchone()
                    if result:
                        topic_ids.append(result[0])
                    else:
                        cursor.execute("INSERT INTO topics (name) VALUES (%s)", (tag,))
                        topic_ids.append(cursor.lastrowid)

                # Associate topics with post
                for topic_id in topic_ids:
                    cursor.execute("INSERT INTO topic_posts (post_id, topic_id) VALUES (%s, %s)", (post_id, topic_id))

                conn.commit()
                return jsonify({"success": True, "post_id": post_id}), 201

            except mysql.connector.Error as err:
                conn.rollback()
                app.logger.error(f"Database transaction error: {err}")
                return jsonify({"error": "Database error during transaction"}), 500

    except mysql.connector.Error as err:
        app.logger.error(f"Database connection error: {err}")
        return jsonify({"error": "Database connection error"}), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(debug=True)
