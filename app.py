from flask import Flask, jsonify,request, g
from flask_cors import CORS  # Import CORS
import requests
import sqlite3

app = Flask(__name__)
# Configure CORS settings
app.config['CORS_RESOURCES'] = {r"/*": {"origins": "*"}}
app.config['CORS_HEADERS'] = 'Content-Type'
app.config['CORS_METHODS'] = ['GET', 'POST', 'PUT', 'DELETE']
cors = CORS(app)

DATABASE = "events.db"

# ------------------- Database Functions -------------------
def get_db():
    """Connect to SQLite database."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

def create_table():
    """Create events table if not exists."""
    with get_db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        time_start TEXT,
                        time_end TEXT)''')
        
        db.execute('''CREATE TABLE IF NOT EXISTS characters (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        element TEXT,
                        gw_rating REAL,
                        gw_rating_grind REAL,
                        gw_rating_fa REAL,
                        gw_rating_hl REAL
                    )''')
        
def update_event(event_id, name, time_start, time_end):
    """Update event in the database."""
    with get_db() as db:
        db.execute('''UPDATE events 
                      SET name = ?, time_start = ?, time_end = ? 
                      WHERE id = ?''', (name, time_start, time_end, event_id))
        db.commit()

def save_events(events):
    """Save events to database."""
    with get_db() as db:
        # First, check for existing events and only insert new ones
        for event in events:
            name, time_start, time_end = event
            # Check if this event already exists, handling NULL values properly
            if time_end:
                cursor = db.execute(
                    'SELECT id FROM events WHERE name = ? AND time_start = ? AND time_end = ?',
                    (name, time_start, time_end)
                )
            else:
                cursor = db.execute(
                    'SELECT id FROM events WHERE name = ? AND time_start = ? AND (time_end IS NULL OR time_end = "")',
                    (name, time_start)
                )
            
            if not cursor.fetchone():
                # Event doesn't exist, insert it
                db.execute(
                    'INSERT INTO events (name, time_start, time_end) VALUES (?, ?, ?)',
                    (name, time_start, time_end)
                )
        db.commit()

def get_stored_events():
    """Retrieve stored events from database."""
    with get_db() as db:
        cur = db.execute('SELECT name, time_start, time_end FROM events')
        return [{"name": row[0], "time_start": row[1], "time_end": row[2]} for row in cur.fetchall()]

def save_characters(characters):
    """Save characters to the database."""
    with get_db() as db:
        # Check for existing characters and only insert new ones
        for character in characters:
            name, element, gw_rating, gw_rating_grind, gw_rating_fa, gw_rating_hl = character
            # Check if this character already exists
            cursor = db.execute('SELECT id FROM characters WHERE name = ? AND element = ?', (name, element))
            if cursor.fetchone():
                # Character exists, update it
                db.execute('''UPDATE characters 
                              SET gw_rating = ?, gw_rating_grind = ?, gw_rating_fa = ?, gw_rating_hl = ? 
                              WHERE name = ? AND element = ?''', 
                           (gw_rating, gw_rating_grind, gw_rating_fa, gw_rating_hl, name, element))
            else:
                # Character doesn't exist, insert it
                db.execute('''INSERT INTO characters 
                              (name, element, gw_rating, gw_rating_grind, gw_rating_fa, gw_rating_hl) 
                              VALUES (?, ?, ?, ?, ?, ?)''', character)
        db.commit()

@app.teardown_appcontext
def close_connection(exception):
    """Close database connection when app context ends."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ------------------- Fetch Events from GBF Wiki -------------------
@app.route('/update-events', methods=['POST'])
def fetch_and_store_events():
    """Fetch events from GBF Wiki and store in database."""
    url = "https://gbf.wiki/api.php"
    headers = {
        "User-Agent": "MyProjectBot/1.0 (contact@example.com)"
    }
    params = {
        'action': 'cargoquery',
        'format': 'json',
        'tables': 'event_history',
        'fields': 'name, time_start, time_end',
        'order_by': 'time_start DESC',
        'limit': '20'
    }

    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        data = response.json()
        events = [
            (
                event['title']['name'],
                event['title']['time start'],
                event['title'].get('time end', 'Ongoing')  # Handle missing end time
            )
            for event in data['cargoquery']
        ]
        
        # Store in DB
        save_events(events)
        return jsonify({"message": "Events updated!", "events": events})
    else:
        return jsonify({"error": "Failed to retrieve data"}), response.status_code
    
# ------------------- Fetch and Store Character Data -------------------
@app.route('/update-characters', methods=['POST'])
def fetch_and_store_characters():
    """Fetch character data from GBF Wiki and store in the database."""
    url = "https://gbf.wiki/api.php"
    headers = {"User-Agent": "MyProjectBot/1.0 (contact@example.com)"}
    params = {
        'action': 'cargoquery',
        'format': 'json',
        'limit': '500',
        'tables': 'characters, character_ratings',
        'fields': 'characters.name, characters.element, character_ratings.gw_rating, '
                  'character_ratings.gw_rating_grind, character_ratings.gw_rating_fa, '
                  'character_ratings.gw_rating_hl',
        'where': "characters.rarity='SSR'",
        'join_on': 'characters.id=character_ratings.id',
        'order_by': 'character_ratings.gw_rating+0 DESC'
    }

    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        data = response.json()
        characters = [
            (
                char['title']['name'],
                char['title']['element'],
                char['title'].get('gw rating') if char['title'].get('gw rating') else None,
                char['title'].get('gw rating grind') if char['title'].get('gw rating grind') else None,
                char['title'].get('gw rating fa') if char['title'].get('gw rating fa') else None,
                char['title'].get('gw rating hl') if char['title'].get('gw rating hl') else None
            )
            for char in data['cargoquery']
        ]
        
        # Store in DB
        save_characters(characters)
        return jsonify({"message": "Characters updated!", "characters": characters})
    else:
        return jsonify({"error": "Failed to retrieve character data"}), response.status_code


# ------------------- Get Stored Events -------------------
@app.route('/events', methods=['GET'])
def get_events():
    """Return stored events from database with event_id.""" 
    with get_db() as db:
        cursor = db.execute('SELECT id, name, time_start, time_end FROM events ORDER BY time_start DESC')
        events = cursor.fetchall()

    events_list = [{"event_id": event[0], "name": event[1], "time_start": event[2], "time_end": event[3]} for event in events]
    return jsonify(events_list)

# ------------------- Get Stored Characters -------------------
@app.route('/characters', methods=['GET'])
def get_characters():
    """Return stored characters from the database."""
    with get_db() as db:
        cur = db.execute('SELECT name, element, gw_rating, gw_rating_grind, gw_rating_fa, gw_rating_hl FROM characters')
        characters = cur.fetchall()

    characters_list = [
        {
            "name": char[0],
            "element": char[1],
            "gw_rating": char[2],
            "gw_rating_grind": char[3],
            "gw_rating_fa": char[4],
            "gw_rating_hl": char[5]
        }
        for char in characters
    ]
    return jsonify(characters_list)

# ------------------- Manually Add a New Event -------------------
@app.route('/add-event', methods=['POST'])
def add_event():
    """Add a new event to the database."""
    data = request.get_json()
    name = data.get('name')
    time_start = data.get('time_start')
    time_end = data.get('time_end', 'Ongoing')  # Default to 'Ongoing' if no end time is provided

    if name and time_start:
        with get_db() as db:
            db.execute('INSERT INTO events (name, time_start, time_end) VALUES (?, ?, ?)', 
                       (name, time_start, time_end))
            db.commit()
        return jsonify({"message": "Event added successfully!"}), 201
    else:
        return jsonify({"error": "Missing required fields (name, time_start)."}), 400

# ------------------- Update an Existing Event -------------------
@app.route('/update-event/<int:event_id>', methods=['PUT'])
def update_event_route(event_id):
    """Update an existing event in the database."""
    data = request.get_json()
    name = data.get('name')
    time_start = data.get('time_start')
    time_end = data.get('time_end', 'Ongoing')

    if name and time_start:
        update_event(event_id, name, time_start, time_end)
        return jsonify({"message": "Event updated successfully!"})
    else:
        return jsonify({"error": "Missing required fields (name, time_start)."}), 400
    
# ------------------- Delete Event -------------------
@app.route('/delete-event/<int:event_id>', methods=['DELETE'])
def delete_event(event_id):
    """Delete an event from the database by its ID."""
    with get_db() as db:
        # Check if the event exists first
        cur = db.execute('SELECT id FROM events WHERE id = ?', (event_id,))
        event = cur.fetchone()
        
        if event is None:
            return jsonify({"error": f"Event with ID {event_id} not found."}), 404

        # If event exists, delete it
        db.execute('DELETE FROM events WHERE id = ?', (event_id,))
        db.commit()
        
    return jsonify({"message": f"Event {event_id} deleted successfully."})

# ------------------- Clean Up Duplicate Entries -------------------
@app.route('/cleanup-duplicates', methods=['POST'])
def cleanup_duplicates():
    """Remove duplicate entries from the database."""
    with get_db() as db:
        # For events, find records with duplicate content but different IDs
        # This should only happen if there was a bug in the save_events function
        # Use IFNULL to properly handle NULL values in time_end
        cursor = db.execute('''
            SELECT e1.id, e1.name, e1.time_start, e1.time_end
            FROM events e1
            JOIN (
                SELECT name, time_start, IFNULL(time_end, '') as time_end, COUNT(*) as count
                FROM events
                GROUP BY name, time_start, IFNULL(time_end, '')
                HAVING count > 1
            ) e2 ON e1.name = e2.name AND e1.time_start = e2.time_start AND IFNULL(e1.time_end, '') = e2.time_end
            ORDER BY e1.name, e1.time_start, e1.id
        ''')
        events_to_check = cursor.fetchall()
        
        # Group by content and keep only the lowest ID for each group
        event_groups = {}
        for event in events_to_check:
            event_id, name, time_start, time_end = event
            key = (name, time_start, time_end if time_end else '')  # Handle None values
            if key not in event_groups:
                event_groups[key] = []
            event_groups[key].append(event_id)
        
        # Delete all but the lowest ID for each group
        deleted_count = 0
        for key, ids in event_groups.items():
            if len(ids) > 1:
                # Keep the lowest ID, delete the rest
                id_to_keep = min(ids)
                for id_to_delete in ids:
                    if id_to_delete != id_to_keep:
                        db.execute('DELETE FROM events WHERE id = ?', (id_to_delete,))
                        deleted_count += 1
        
        # For characters, similar approach
        cursor = db.execute('''
            SELECT c1.id, c1.name, c1.element
            FROM characters c1
            JOIN (
                SELECT name, element, COUNT(*) as count
                FROM characters
                GROUP BY name, element
                HAVING count > 1
            ) c2 ON c1.name = c2.name AND c1.element = c2.element
            ORDER BY c1.name, c1.element, c1.id
        ''')
        chars_to_check = cursor.fetchall()
        
        # Group by content and keep only the lowest ID for each group
        char_groups = {}
        for char in chars_to_check:
            char_id, name, element = char
            key = (name, element)
            if key not in char_groups:
                char_groups[key] = []
            char_groups[key].append(char_id)
        
        # Delete all but the lowest ID for each group
        char_deleted_count = 0
        for key, ids in char_groups.items():
            if len(ids) > 1:
                # Keep the lowest ID, delete the rest
                id_to_keep = min(ids)
                for id_to_delete in ids:
                    if id_to_delete != id_to_keep:
                        db.execute('DELETE FROM characters WHERE id = ?', (id_to_delete,))
                        char_deleted_count += 1
        
        db.commit()
        
    return jsonify({
        "message": "Cleanup completed",
        "events_deleted": deleted_count,
        "characters_deleted": char_deleted_count
    })

# ------------------- Run App -------------------
if __name__ == '__main__':
    with app.app_context():  # Make sure we run the context
        create_table()  # Ensure table exists before starting
        
        # Update data on startup
        print("Updating events data from GBF Wiki...")
        try:
            # Call the function directly instead of through the route
            url = "https://gbf.wiki/api.php"
            headers = {
                "User-Agent": "MyProjectBot/1.0 (contact@example.com)"
            }
            params = {
                'action': 'cargoquery',
                'format': 'json',
                'tables': 'event_history',
                'fields': 'name, time_start, time_end',
                'order_by': 'time_start DESC',
                'limit': '20'
            }

            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                events = [
                    (
                        event['title']['name'],
                        event['title']['time start'],
                        event['title'].get('time end', 'Ongoing')  # Handle missing end time
                    )
                    for event in data['cargoquery']
                ]
                
                # Store in DB
                save_events(events)
                print(f"Successfully updated {len(events)} events")
            else:
                print(f"Failed to retrieve events data: {response.status_code}")
        except Exception as e:
            print(f"Error updating events data: {e}")
            
        print("Updating character data from GBF Wiki...")
        try:
            # Call the character update function directly
            url = "https://gbf.wiki/api.php"
            headers = {"User-Agent": "MyProjectBot/1.0 (contact@example.com)"}
            params = {
                'action': 'cargoquery',
                'format': 'json',
                'limit': '500',
                'tables': 'characters, character_ratings',
                'fields': 'characters.name, characters.element, character_ratings.gw_rating, '
                        'character_ratings.gw_rating_grind, character_ratings.gw_rating_fa, '
                        'character_ratings.gw_rating_hl',
                'where': "characters.rarity='SSR'",
                'join_on': 'characters.id=character_ratings.id',
                'order_by': 'character_ratings.gw_rating+0 DESC'
            }

            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                characters = [
                    (
                        char['title']['name'],
                        char['title']['element'],
                        char['title'].get('gw rating') if char['title'].get('gw rating') else None,
                        char['title'].get('gw rating grind') if char['title'].get('gw rating grind') else None,
                        char['title'].get('gw rating fa') if char['title'].get('gw rating fa') else None,
                        char['title'].get('gw rating hl') if char['title'].get('gw rating hl') else None
                    )
                    for char in data['cargoquery']
                ]
                
                # Store in DB
                save_characters(characters)
                print(f"Successfully updated {len(characters)} characters")
            else:
                print(f"Failed to retrieve character data: {response.status_code}")
        except Exception as e:
            print(f"Error updating character data: {e}")
            
        # Clean up any duplicate entries that might exist
        print("Cleaning up duplicate entries...")
        try:
            # Find duplicate events with different IDs
            # Use IFNULL to properly handle NULL values in time_end
            cursor = get_db().execute('''
                SELECT e1.id, e1.name, e1.time_start, e1.time_end
                FROM events e1
                JOIN (
                    SELECT name, time_start, IFNULL(time_end, '') as time_end, COUNT(*) as count
                    FROM events
                    GROUP BY name, time_start, IFNULL(time_end, '')
                    HAVING count > 1
                ) e2 ON e1.name = e2.name AND e1.time_start = e2.time_start AND IFNULL(e1.time_end, '') = e2.time_end
                ORDER BY e1.name, e1.time_start, e1.id
            ''')
            events_to_check = cursor.fetchall()
            
            # Group by content and keep only the lowest ID for each group
            event_groups = {}
            for event in events_to_check:
                event_id, name, time_start, time_end = event
                key = (name, time_start, time_end if time_end else '')  # Handle None values
                if key not in event_groups:
                    event_groups[key] = []
                event_groups[key].append(event_id)
            
            # Delete all but the lowest ID for each group
            deleted_count = 0
            for key, ids in event_groups.items():
                if len(ids) > 1:
                    # Keep the lowest ID, delete the rest
                    id_to_keep = min(ids)
                    for id_to_delete in ids:
                        if id_to_delete != id_to_keep:
                            get_db().execute('DELETE FROM events WHERE id = ?', (id_to_delete,))
                            deleted_count += 1
            
            # Find duplicate characters with different IDs
            cursor = get_db().execute('''
                SELECT c1.id, c1.name, c1.element
                FROM characters c1
                JOIN (
                    SELECT name, element, COUNT(*) as count
                    FROM characters
                    GROUP BY name, element
                    HAVING count > 1
                ) c2 ON c1.name = c2.name AND c1.element = c2.element
                ORDER BY c1.name, c1.element, c1.id
            ''')
            chars_to_check = cursor.fetchall()
            
            # Group by content and keep only the lowest ID for each group
            char_groups = {}
            for char in chars_to_check:
                char_id, name, element = char
                key = (name, element)
                if key not in char_groups:
                    char_groups[key] = []
                char_groups[key].append(char_id)
            
            # Delete all but the lowest ID for each group
            char_deleted_count = 0
            for key, ids in char_groups.items():
                if len(ids) > 1:
                    # Keep the lowest ID, delete the rest
                    id_to_keep = min(ids)
                    for id_to_delete in ids:
                        if id_to_delete != id_to_keep:
                            get_db().execute('DELETE FROM characters WHERE id = ?', (id_to_delete,))
                            char_deleted_count += 1
            
            get_db().commit()
            
            if deleted_count > 0 or char_deleted_count > 0:
                print(f"Cleanup completed: Removed {deleted_count} duplicate events and {char_deleted_count} duplicate characters")
            else:
                print("No duplicates found")
        except Exception as e:
            print(f"Error cleaning up duplicates: {e}")
            
    # Start the Flask app
    app.run(host='0.0.0.0', port=5000)
