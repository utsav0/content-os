from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import mysql.connector
import os
from dotenv import load_dotenv
import logging

# Load environment variables from .env
load_dotenv()

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app)

# --- Database Configuration ---
db_config = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

@app.route('/post-data')
def post_data():
    return render_template('index.html')

@app.route('/api/posts/ids')
def get_post_ids():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT post_id FROM posts")
        ids = [str(row[0]) for row in cursor.fetchall()]  # convert to string
        return jsonify(ids)
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()


@app.route('/post/<int:post_id>')
def show_post_details(post_id):
    app.logger.info(f"Request received for post with ID: {post_id}")
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        app.logger.info(f"Executing query: SELECT * FROM posts WHERE post_id = {post_id}")
        cursor.execute("SELECT * FROM posts WHERE post_id = %s", (post_id,))
        post = cursor.fetchone()
        app.logger.info(f"Database returned: {post}") # Log the result from the database
        
        if post:
            app.logger.info(f'Successfully fetched post with ID: {post_id}')
            return render_template('post_details.html', post=post)
        else:
            app.logger.warning(f'Post with ID {post_id} not found.')
            return "Post not found", 404

    except mysql.connector.Error as err:
        app.logger.error(f"Database error: {err}")
        return "Database error", 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/tags-entry')
def tags_entry():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM posts ORDER BY post_id ASC LIMIT 1")
        post = cursor.fetchone()
        if post:
            return render_template('tags_entry.html', post=post)
        else:
            return "No posts found", 404
    except mysql.connector.Error as err:
        return f"Database error: {err}", 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()


# =====================================================================
# === NEW HELPER FUNCTION TO ASSOCIATE POSTS WITH TOPICS ===
# =====================================================================
def associate_post_with_topics(cursor, post_id, topics_list):
    """
    Associates a given post_id with a list of topic names.
    It creates topics if they don't exist and then links them.
    """
    if not topics_list:
        logging.info(f"No topics provided for post ID {post_id}. Skipping.")
        return

    logging.info(f"Associating post ID {post_id} with topics: {topics_list}")
    
    for topic_name in topics_list:
        try:
            # Step 1: Ensure the topic exists in the 'topics' table.
            # INSERT IGNORE will skip inserting if the topic name already exists.
            cursor.execute("INSERT IGNORE INTO topics (name) VALUES (%s)", (topic_name,))
            
            # Step 2: Get the topic_id for the given topic name.
            cursor.execute("SELECT id FROM topics WHERE name = %s", (topic_name,))
            topic = cursor.fetchone()
            
            if topic:
                topic_id = topic['id']
                # Step 3: Link the post and topic in the junction table.
                # INSERT IGNORE prevents errors if the link already exists.
                cursor.execute(
                    "INSERT IGNORE INTO topic_posts (topic_id, post_id) VALUES (%s, %s)",
                    (topic_id, post_id)
                )
                logging.info(f"  - Linked topic '{topic_name}' (ID: {topic_id}) to post {post_id}")
            else:
                logging.warning(f"  - Could not find or create topic '{topic_name}'")

        except mysql.connector.Error as err:
            logging.error(f"Database error while processing topic '{topic_name}': {err}")


@app.route('/api/next-post', methods=['POST'])
def get_next_post():
    data = request.get_json()
    interests = data.get('interests', [])
    current_post_index = data.get('currentPostIndex', 0)

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        # Get the post_id of the closed post
        closed_post_index = current_post_index - 1
        if closed_post_index >= 0:
            cursor.execute("SELECT post_id FROM posts ORDER BY post_id ASC LIMIT 1 OFFSET %s", (closed_post_index,))
            closed_post = cursor.fetchone()
            if closed_post:
                # ============================================================
                # === THIS IS WHERE THE NEW LOGIC IS CALLED ===
                # ============================================================
                associate_post_with_topics(cursor, closed_post['post_id'], interests)
                conn.commit() # IMPORTANT: Save the changes to the database
                # ============================================================
            else:
                logging.warning(f"Could not find post for index {closed_post_index}")

        # Fetch the next post
        cursor.execute("SELECT * FROM posts ORDER BY post_id ASC LIMIT 1 OFFSET %s", (current_post_index,))
        post = cursor.fetchone()
        if post:
            # Convert post_id to string to avoid JS precision issues
            post['post_id'] = str(post['post_id'])
            # Convert datetime to string for JSON serialization
            if post.get('post_datetime'):
                post['post_datetime'] = post['post_datetime'].isoformat()
            return jsonify(post)
        else:
            return jsonify({"error": "No more posts"}), 404

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()


@app.route('/api/topics')
def get_topics():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM topics ORDER BY name ASC")
        topics = [row[0] for row in cursor.fetchall()]
        return jsonify(topics)
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    app.run(debug=True)
