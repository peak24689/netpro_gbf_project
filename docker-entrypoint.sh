#!/bin/bash

# Start the Flask app in the background
python app.py &

# Wait for Flask to start
sleep 5

# Start the event notifier
python event_notifier.py 