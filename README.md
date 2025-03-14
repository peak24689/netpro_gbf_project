# GBF Event Tracker and Character Recommender

A Dockerized application for tracking Granblue Fantasy (GBF) events and providing character recommendations. The system includes real-time event notifications via MQTT and character recommendations based on various criteria.

## Features

- Real-time GBF event tracking
- MQTT-based event notifications
- Character recommendations based on:
  - Element (Fire, Water, Earth, Wind, Light, Dark)
  - Rating type (general, grind, full-auto, high-level)
- Persistent data storage
- RESTful API endpoints
- AI-powered character recommendations using DeepSeek model
- Duplicate data prevention and cleanup functionality
- Automatic data updates on application startup

## Prerequisites

- Docker
- Docker Compose
- Git (for cloning the repository)
- DeepSeek AI model (r1:1.5b) running locally or accessible via API

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd netpro_gbf_project
```

2. Set up DeepSeek AI model:
   - Install Ollama (https://ollama.ai) for running the DeepSeek model locally
   - Pull the DeepSeek model:
   ```bash
   ollama pull deepseek-r1:1.5b
   ```
   - Start the Ollama service:
   ```bash
   ollama serve
   ```
   - **Note**: The Docker setup is configured to connect to Ollama running on your host machine using `host.docker.internal`. This works on Windows and macOS. For Linux, you may need to modify the `DEEPSEEK_API_URL` in docker-compose.yml.

3. Build and start the containers:
```bash
docker-compose up --build
```

To run in detached mode (background):
```bash
docker-compose up -d --build
```

## Usage

### Event Tracking

The system automatically tracks GBF events and sends notifications through MQTT. You can subscribe to the following MQTT topics using the recommended method:

```bash
# View all event topics (recommended method)
docker exec -it netpro_gbf_project-mosquitto-1 mosquitto_sub -t "gbf/events/#" -v

# Or subscribe to specific topics:
docker exec -it netpro_gbf_project-mosquitto-1 mosquitto_sub -t "gbf/events/current" -v
docker exec -it netpro_gbf_project-mosquitto-1 mosquitto_sub -t "gbf/events/upcoming" -v
docker exec -it netpro_gbf_project-mosquitto-1 mosquitto_sub -t "gbf/events/ending_soon" -v
docker exec -it netpro_gbf_project-mosquitto-1 mosquitto_sub -t "gbf/events/starting_soon" -v
```

Available MQTT topics:
- `gbf/events/current`: Currently active events
- `gbf/events/upcoming`: Upcoming events
- `gbf/events/ending_soon`: Events ending within 24 hours
- `gbf/events/starting_soon`: Events starting within 3 days

### Important Note About Docker Commands

**All Docker Compose commands must be run from the project directory** (where the `docker-compose.yml` file is located). This includes commands for running the character recommender, checking logs, or interacting with the containers in any way.

For example:
```bash
# Navigate to the project directory first
cd path/to/netpro_gbf_project

# Then run Docker Compose commands
docker-compose exec app python deepseek_recommender.py --element Fire --rating general
```

If you try to run Docker Compose commands from a different directory, you'll get errors because Docker Compose won't be able to find the project configuration.

### Character Recommendations

To get character recommendations, use the following command:

```bash
docker-compose exec app python deepseek_recommender.py [options]
```

Available options:
- `--element`: Filter by element (Fire, Water, Earth, Wind, Light, Dark)
- `--rating`: Filter by rating type (general, grind, full-auto, high-level)
- `--limit`: Limit the number of characters to analyze

Examples:
```bash
# Get general recommendations for Fire characters
docker-compose exec app python deepseek_recommender.py --element Fire --rating general

# Get grind recommendations for Water characters
docker-compose exec app python deepseek_recommender.py --element Water --rating grind

# Get recommendations for all elements with high-level rating
docker-compose exec app python deepseek_recommender.py --rating high-level
```

### API Endpoints

The Flask API provides the following endpoints:

- `GET /events`: Get all stored events
- `POST /update-events`: Fetch and update events from GBF Wiki
- `GET /characters`: Get all stored characters
- `POST /update-characters`: Fetch and update character data from GBF Wiki
- `POST /add-event`: Manually add a new event
- `PUT /update-event/<event_id>`: Update an existing event
- `DELETE /delete-event/<event_id>`: Delete an event
- `POST /cleanup-duplicates`: Remove duplicate entries from the database

## Configuration

### Environment Variables

The following environment variables can be configured in the `docker-compose.yml` file:

- `MQTT_BROKER`: MQTT broker address (default: mosquitto)
- `MQTT_PORT`: MQTT broker port (default: 1883)
- `API_BASE_URL`: Flask API base URL (default: http://app:5000)
- `DEEPSEEK_API_URL`: DeepSeek API URL (default: http://host.docker.internal:11434/api/chat)

### DeepSeek Configuration

The character recommender uses the DeepSeek AI model for generating recommendations. You can configure the model settings in `deepseek_recommender.py`:

```python
data = {
    "model": "deepseek-r1:1.5b",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant that provides character recommendations based on game data."},
        {"role": "user", "content": f"Here is the character data: {json.dumps(characters_data)}. Based on this, can you recommend the top 3 characters?"}
    ],
    "stream": False
}
```

### MQTT Configuration

MQTT configuration can be modified in the `mosquitto.conf` file. By default, it allows anonymous connections. To add authentication, modify the configuration file and update the environment variables accordingly.

## Data Management

### Data Persistence

The following data is persisted between container restarts:
- Events database (`events.db`)
- MQTT data and logs (stored in Docker volumes)

### Automatic Data Updates

The application automatically performs the following operations on startup:

1. **Update Events**: Fetches the latest event data from the GBF Wiki and updates the database
2. **Update Characters**: Fetches the latest character data and ratings from the GBF Wiki
3. **Cleanup Duplicates**: Automatically removes any duplicate entries in the database

This ensures that your database is always up-to-date with the latest information whenever the application starts, without requiring manual API calls.

### Duplicate Data Prevention

The application includes mechanisms to prevent duplicate entries in the database:

1. **Event Data**: When fetching events from the GBF Wiki, the system checks if an event with the same name, start time, and end time already exists before inserting it.

2. **Character Data**: When fetching character data, the system checks if a character with the same name and element already exists. If it does, the system updates the existing record instead of creating a duplicate.

3. **Cleanup Endpoint**: A dedicated endpoint (`/cleanup-duplicates`) is available to remove any existing duplicate entries in the database. This endpoint:
   - Identifies duplicate events based on name, start time, and end time
   - Identifies duplicate characters based on name and element
   - Keeps the record with the lowest ID and removes all duplicates
   - Returns a count of deleted entries

To clean up existing duplicates, use:
```bash
curl -X POST http://localhost:5000/cleanup-duplicates
```

## Troubleshooting

1. If you get errors like "No such service" or "Cannot find a docker-compose.yml file":
   - Make sure you're running all Docker Compose commands from the project directory (where the docker-compose.yml file is located)
   - Navigate to the project directory first:
     ```bash
     cd path/to/netpro_gbf_project
     ```
   - Then run your Docker Compose commands

2. If the containers fail to start:
   ```bash
   docker-compose down
   docker-compose up --build
   ```

3. To view logs:
   ```bash
   docker-compose logs -f
   ```

4. To check container status:
   ```bash
   docker-compose ps
   ```

5. Flask dependency issues:
   - If you see an error like `ImportError: cannot import name 'url_quote' from 'werkzeug.urls'`, the requirements.txt file has been updated to fix this by pinning werkzeug to version 2.0.3.
   - Run `docker-compose build --no-cache` to rebuild the containers with the updated dependencies.

6. MQTT connection issues:
   - If the event notifier can't connect to the MQTT broker, check that the broker is running:
     ```bash
     docker-compose logs mosquitto
     ```
   - The Docker setup uses service names for networking. If you're running the services separately, update the `MQTT_BROKER` environment variable.
   - **RECOMMENDED METHOD**: Use mosquitto_sub directly from the mosquitto container:
     ```bash
     # This is the most reliable method to view MQTT messages
     docker exec -it netpro_gbf_project-mosquitto-1 mosquitto_sub -t "gbf/events/#" -v
     ```
   - To publish a test message and verify your subscription is working:
     ```bash
     # Publish a test message with the retain flag
     docker exec -it netpro_gbf_project-mosquitto-1 mosquitto_pub -t "gbf/events/test" -m "Test message" -r
     ```
   - If you're still not seeing any messages, force an event update:
     ```bash
     # Trigger event updates to generate MQTT messages
     curl -X POST http://localhost:5000/update-events
     ```
   - See the detailed MQTT troubleshooting section in [testing.txt](testing.txt#31-mqtt-subscription-troubleshooting) for more options.

7. DeepSeek API connection:
   - If the character recommender can't connect to the DeepSeek API, make sure Ollama is running on your host machine.
   - For Linux hosts, you may need to modify the `DEEPSEEK_API_URL` in docker-compose.yml to use the host's IP address instead of `host.docker.internal`.
   - Test the Ollama API directly:
     ```bash
     curl -X POST http://localhost:11434/api/chat -d '{"model":"deepseek-r1:1.5b","messages":[{"role":"user","content":"Hello"}]}'
     ```

8. Duplicate data issues:
   - If you notice duplicate entries in the database, run the cleanup endpoint:
     ```bash
     curl -X POST http://localhost:5000/cleanup-duplicates
     ```
   - The system has been updated to prevent new duplicates from being created when fetching data from the GBF Wiki.
   - If duplicates persist after cleanup, please check for any custom scripts or processes that might be inserting data without duplicate checking.

## Testing

For comprehensive testing instructions, please refer to [testing.txt](testing.txt). This document includes detailed testing procedures for:
- Basic setup verification
- API endpoint testing
- MQTT notification testing
- Character recommender testing
- DeepSeek API integration testing
- Database operations
- Integration testing
- Error handling scenarios
- Performance monitoring
- Security testing

## Stopping the Application

To stop the application:
```bash
docker-compose down
```

To stop and remove all data:
```bash
docker-compose down -v
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License
