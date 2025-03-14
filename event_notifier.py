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


def publish_events(client, categorized_events):
    """Publish events to their respective MQTT topics"""
    # Publish current events
    client.publish(
        TOPIC_CURRENT_EVENTS, 
        json.dumps(categorized_events["current"]), 
        qos=1, 
        retain=True
    )
    logger.info(f"Published {len(categorized_events['current'])} current events")

    # Publish upcoming events
    client.publish(
        TOPIC_UPCOMING_EVENTS, 
        json.dumps(categorized_events["upcoming"]), 
        qos=1, 
        retain=True
    )
    logger.info(f"Published {len(categorized_events['upcoming'])} upcoming events")

    # Publish events ending soon
    client.publish(
        TOPIC_ENDING_SOON, 
        json.dumps(categorized_events["ending_soon"]), 
        qos=1, 
        retain=True
    )
    logger.info(f"Published {len(categorized_events['ending_soon'])} events ending soon")

    # Publish events starting soon
    client.publish(
        TOPIC_STARTING_SOON, 
        json.dumps(categorized_events["starting_soon"]), 
        qos=1, 
        retain=True
    )
    logger.info(f"Published {len(categorized_events['starting_soon'])} events starting soon")


def main():
    """Main function to run the event notifier"""
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
                    categorized_events = categorize_events(events)
                    
                    # Publish to MQTT topics
                    publish_events(client, categorized_events)
                    
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