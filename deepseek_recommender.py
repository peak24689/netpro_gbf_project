import sqlite3
import requests
import json
import argparse
import os

# Mapping between user input (rating) and the corresponding database column
focus_mapping = {
    'general': 'gw_rating',
    'grind': 'gw_rating_grind',
    'full-auto': 'gw_rating_fa',
    'high-level': 'gw_rating_hl'
}

# Fetch character data from SQLite database
def get_character_data(filter_element=None, filter_rating=None, limit=None):
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    query = "SELECT * FROM characters WHERE 1=1"
    
    # Apply filters if they exist
    if filter_element:
        query += f" AND element = '{filter_element}'"
    
    # Apply rating filter if it exists, using the focus_mapping to get the correct column
    if filter_rating and filter_rating in focus_mapping:
        rating_column = focus_mapping[filter_rating]
        query += f" AND {rating_column} IS NOT NULL"  # Ensure we filter out characters with no rating
        query += f" ORDER BY {rating_column} DESC"  # Sort by the specified rating in descending order
    else:
        query += " ORDER BY gw_rating+0 DESC"  # Default sort by general rating
    
    # Limit the number of results if needed
    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    characters = cursor.fetchall()
    conn.close()

    # Return character data as a list of dictionaries
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in characters]

# Send data to DeepSeek and get recommendations
def get_deepseek_recommendations(characters_data, rating_type=None):
    url = os.environ.get("DEEPSEEK_API_URL", "http://localhost:11434/api/chat")
    
    # Define explanations for each rating type
    rating_explanations = {
        'general': "General rating represents the character's overall usefulness in most content.",
        'grind': "Grind rating represents how effective the character is for grinding repetitive content efficiently.",
        'full-auto': "Full-auto rating represents how well the character performs when the game is played on automatic mode without manual inputs.",
        'high-level': "High-level rating represents how valuable the character is for difficult endgame content."
    }
    
    # Create a more specific prompt based on the rating type
    if rating_type and rating_type in focus_mapping:
        rating_column = focus_mapping[rating_type]
        explanation = rating_explanations.get(rating_type, "")
        
        prompt = f"""Here is the character data: {json.dumps(characters_data)}. 

I need recommendations for the top 3 characters specifically focusing on their '{rating_column}' values.

{explanation}

Please prioritize characters with higher values in this specific rating category and explain why they excel in this area."""
    else:
        prompt = f"""Here is the character data: {json.dumps(characters_data)}. 

Please recommend the top 3 characters based on their overall ratings (gw_rating).

The general rating represents a character's overall usefulness across different content types."""
    
    data = {
        "model": "deepseek-r1:1.5b",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that provides character recommendations for Granblue Fantasy based on game data. The ratings are on a scale from 1-10, with 10 being the best."},
            {"role": "user", "content": prompt}
        ],
        "stream": False
    }
    
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, headers=headers, data=json.dumps(data))
    
    if response.status_code == 200:
        result = response.json()  # Parse the response as JSON
        #print("Raw response:", result)  # Add this line to print the response for debugging
        
        message = result["message"]["content"]
        
        cleaned_message = message.replace("<think>", "").replace("</think>", "").strip()
        
        return cleaned_message
    else:
        print("Error:", response.status_code, response.text)
        return None


def main():
    # Command-line argument parsing
    parser = argparse.ArgumentParser(description="Get Granblue Fantasy character recommendations")
    parser.add_argument('--element', type=str, choices=['Fire', 'Water', 'Earth', 'Wind', 'Light', 'Dark'], 
                        help="Filter by element")
    parser.add_argument('--rating', type=str, choices=['general', 'grind', 'full-auto', 'high-level'], 
                        help="Filter by rating")
    parser.add_argument('--limit', type=int, help="Limit the number of characters to analyze")
    
    args = parser.parse_args()
    
    # Fetch character data from the SQLite database
    characters = get_character_data(args.element, args.rating, args.limit)
    
    # Send data to DeepSeek for analysis, including the rating type
    recommendations = get_deepseek_recommendations(characters, args.rating)

    # Output the recommendations
    print('recommendations:',recommendations)

if __name__ == '__main__':
    main()
