import paho.mqtt.client as mqtt
import requests
import json
import time
import datetime
import logging
from dateutil import parser
from dateutil import tz
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("event_notifier.log"), logging.StreamHandler()]
)
logger = logging.getLogger("event_notifier")

# Configuration
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:5000")  # Update with your Flask API URL
MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")  # Use Docker service name
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_TOPIC_PREFIX = "gbf/events/"
MQTT_CLIENT_ID = "gbf-event-notifier"
MQTT_USERNAME = None  # Set if your broker requires authentication
MQTT_PASSWORD = None  # Set if your broker requires authentication
# Control message format: 'human' for readable format, 'json' for JSON format
MESSAGE_FORMAT = os.environ.get("MESSAGE_FORMAT", "human").lower()
# Whether to include event IDs in the output
INCLUDE_EVENT_IDS = os.environ.get("INCLUDE_EVENT_IDS", "false").lower() == "true"

CHECK_INTERVAL = 3600  # Check every hour (in seconds)

# Define notification topics
TOPIC_CURRENT_EVENTS = f"{MQTT_TOPIC_PREFIX}current"
TOPIC_UPCOMING_EVENTS = f"{MQTT_TOPIC_PREFIX}upcoming"
TOPIC_ENDING_SOON = f"{MQTT_TOPIC_PREFIX}ending_soon"
TOPIC_STARTING_SOON = f"{MQTT_TOPIC_PREFIX}starting_soon"

# Define timezone info for JST
TZINFOS = {"JST": tz.gettz("Asia/Tokyo")}


def on_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT broker"""
    if rc == 0:
        logger.info("Connected to MQTT broker")
    else:
        logger.error(f"Failed to connect to MQTT broker with code {rc}")


def on_publish(client, userdata, mid):
    """Callback when message is published"""
    logger.debug(f"Message {mid} published")


def parse_event_date(date_str):
    """Parse date string to datetime object"""
    try:
        if date_str is None or date_str == "":
            logger.warning("Empty date string, using far future date")
            # Make sure our default date is timezone naive
            return datetime.datetime.now() + datetime.timedelta(days=365)
        
        if date_str == "Ongoing":
            # Set a far future date for ongoing events, timezone naive
            return datetime.datetime.now() + datetime.timedelta(days=365)
        
        # Parse with timezone info
        dt = parser.parse(date_str, tzinfos=TZINFOS)
        
        # Convert to naive datetime to avoid timezone comparison issues
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
            
        return dt
    except Exception as e:
        logger.error(f"Error parsing date '{date_str}': {e}")
        # Return a far future date as fallback
        return datetime.datetime.now() + datetime.timedelta(days=365)


def get_events():
    """Fetch events from the API"""
    try:
        response = requests.get(f"{API_BASE_URL}/events")
        if response.status_code == 200:
            events = response.json()
            
            # Log the first event for debugging
            if events and len(events) > 0:
                logger.info(f"Sample event data: {json.dumps(events[0], indent=2)}")
                
            return events
        else:
            logger.error(f"API returned status code {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Error fetching events: {e}")
        return []


def categorize_events(events):
    """Categorize events into current, upcoming, ending soon, and starting soon"""
    now = datetime.datetime.now()  # Use naive datetime
    one_day_later = now + datetime.timedelta(days=1)
    three_days_later = now + datetime.timedelta(days=3)

    current_events = []
    upcoming_events = []
    ending_soon = []
    starting_soon = []

    for event in events:
        # Ensure time_start and time_end exist in the event data
        if "time_start" not in event or event["time_start"] is None:
            logger.warning(f"Event missing time_start field: {json.dumps(event)}")
            continue
            
        if "time_end" not in event or event["time_end"] is None:
            logger.warning(f"Event missing time_end field, using 'Ongoing' as default")
            event["time_end"] = "Ongoing"

        try:
            start_time = parse_event_date(event["time_start"])
            end_time = parse_event_date(event["time_end"])
            
            # Current events: started but not ended
            if start_time <= now and end_time > now:
                current_events.append(event)
                
                # Ending soon: current events ending within 24 hours
                if end_time <= one_day_later:
                    ending_soon.append(event)

            # Upcoming events: not started yet
            elif start_time > now:
                upcoming_events.append(event)
                
                # Starting soon: upcoming events starting within 3 days
                if start_time <= three_days_later:
                    starting_soon.append(event)
        except Exception as e:
            logger.error(f"Error categorizing event {event['name'] if 'name' in event else 'unknown'}: {e}")
            continue

    return {
        "current": current_events,
        "upcoming": upcoming_events,
        "ending_soon": ending_soon,
        "starting_soon": starting_soon
    }


def format_events(events):
    """Format events to be more compact and readable"""
    if not events:
        return "No events"
        
    formatted = []
    for event in events:
        try:
            # Extract only essential information
            name = event.get("name", "Unnamed")
            event_id = event.get("event_id", "")
            
            # Get date strings
            start = event.get("time_start", "Unknown")
            end = event.get("time_end", "Unknown")
            
            # Format dates to be more concise
            if isinstance(start, str):
                start = start.replace(" JST", "")
                if "2025-" in start:
                    start = start.replace("2025-", "")
                    
            if isinstance(end, str):
                end = end.replace(" JST", "")
                if "2025-" in end:
                    end = end.replace("2025-", "")
            
            # Include ID if configured
            id_prefix = f"[{event_id}] " if INCLUDE_EVENT_IDS and event_id else ""
            
            # Format differently depending on if it's "Ongoing" or not
            if end == "Ongoing":
                formatted.append(f"• {id_prefix}{name} (Starts: {start})")
            else:
                formatted.append(f"• {id_prefix}{name}\n  {start} → {end}")
        except Exception as e:
            logger.error(f"Error formatting event: {e}")
            # Add basic info for problematic event
            formatted.append(f"• Error formatting event: {event.get('name', 'Unknown event')}")
        
    return "\n".join(formatted)


def publish_events(client, categorized_events):
    """Publish events to their respective MQTT topics"""
    
    # Determine which format to use
    use_json = MESSAGE_FORMAT == "json"
    
    # Publish current events
    payload = json.dumps(categorized_events["current"]) if use_json else format_events(categorized_events["current"])
    client.publish(TOPIC_CURRENT_EVENTS, payload, qos=1, retain=True)
    logger.info(f"Published {len(categorized_events['current'])} current events")

    # Publish upcoming events
    payload = json.dumps(categorized_events["upcoming"]) if use_json else format_events(categorized_events["upcoming"])
    client.publish(TOPIC_UPCOMING_EVENTS, payload, qos=1, retain=True)
    logger.info(f"Published {len(categorized_events['upcoming'])} upcoming events")

    # Publish events ending soon
    payload = json.dumps(categorized_events["ending_soon"]) if use_json else format_events(categorized_events["ending_soon"])
    client.publish(TOPIC_ENDING_SOON, payload, qos=1, retain=True)
    logger.info(f"Published {len(categorized_events['ending_soon'])} events ending soon")

    # Publish events starting soon
    payload = json.dumps(categorized_events["starting_soon"]) if use_json else format_events(categorized_events["starting_soon"])
    client.publish(TOPIC_STARTING_SOON, payload, qos=1, retain=True)
    logger.info(f"Published {len(categorized_events['starting_soon'])} events starting soon")


def main():
    """Main function to run the event notifier"""
    # Log configuration
    logger.info("Configuration:")
    logger.info(f"- API Base URL: {API_BASE_URL}")
    logger.info(f"- MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    logger.info(f"- Check Interval: {CHECK_INTERVAL} seconds")
    logger.info(f"- Message Format: {MESSAGE_FORMAT}")
    logger.info(f"- Include Event IDs: {INCLUDE_EVENT_IDS}")
    
    # Set up MQTT client
    client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    client.on_connect = on_connect
    client.on_publish = on_publish

    # Set username and password if provided
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    try:
        # Connect to broker
        logger.info(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        
        # Start the loop
        client.loop_start()

        while True:
            try:
                # Fetch events
                logger.info("Fetching events from API")
                events = get_events()
                
                if events:
                    # Categorize events
                    logger.info(f"Found {len(events)} events from API")
                    categorized_events = categorize_events(events)
                    
                    # Show counts
                    logger.info(f"Event counts by category:")
                    logger.info(f"- Current events: {len(categorized_events['current'])}")
                    logger.info(f"- Upcoming events: {len(categorized_events['upcoming'])}")
                    logger.info(f"- Ending soon: {len(categorized_events['ending_soon'])}")
                    logger.info(f"- Starting soon: {len(categorized_events['starting_soon'])}")
                    
                    # Publish to MQTT topics
                    publish_events(client, categorized_events)
                    
                    # Log samples of the formatted output if human format is used
                    if MESSAGE_FORMAT == "human" and categorized_events["current"]:
                        sample_output = format_events([categorized_events["current"][0]])
                        logger.info(f"Sample formatted output:\n{sample_output}")
                    
                    # Log important notifications
                    if categorized_events["ending_soon"]:
                        logger.info("ALERT: Events ending in 24 hours:")
                        for event in categorized_events["ending_soon"]:
                            logger.info(f"  - {event['name'] if 'name' in event else 'unnamed'} (ends: {event['time_end']})")
                    
                    if categorized_events["starting_soon"]:
                        logger.info("NOTICE: Events starting in 3 days:")
                        for event in categorized_events["starting_soon"]:
                            logger.info(f"  - {event['name'] if 'name' in event else 'unnamed'} (starts: {event['time_start']})")
                else:
                    logger.warning("No events returned from API")
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                # Continue despite errors in the main processing loop
            
            # Wait for next check interval
            logger.info(f"Next check in {CHECK_INTERVAL} seconds")
            time.sleep(CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("Script terminated by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        # Clean up
        client.loop_stop()
        client.disconnect()
        logger.info("Disconnected from MQTT broker")


if __name__ == "__main__":
    logger.info("Starting GBF Event Notifier")
    main()