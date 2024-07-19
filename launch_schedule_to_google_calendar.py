import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import re
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_launch_schedule():
    url = "https://spaceflightnow.com/launch-schedule/"
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    launches = []

    for launch in soup.find_all('div', class_='datename'):
        date_str = launch.find('span', class_='launchdate').text.strip()
        date_str = re.sub(r'^NET\s+', '', date_str)
        date_str = re.sub(r'\s+$', '', date_str)

        try:
            date_obj = datetime.strptime(date_str, "%B %d, %Y")
        except ValueError:
            try:
                date_obj = datetime.strptime(date_str, "%B %d")
                date_obj = date_obj.replace(year=datetime.now().year)
            except ValueError:
                logging.warning(f"Date format not recognized: {date_str}")
                continue
        
        time_element = launch.find_next('span', class_='launchdate')
        time_str = None
        if time_element and time_element.next_sibling:
            time_str = time_element.next_sibling.strip()

        if not time_str:
            time_str = "00:00 UTC"

        try:
            time_obj = datetime.strptime(time_str, "%H:%M %Z")
        except ValueError:
            logging.warning(f"Time format not recognized: {time_str}, defaulting to 00:00 UTC")
            time_obj = datetime.strptime("00:00 UTC", "%H:%M %Z")
        
        mission_element = launch.find_next_sibling('div', class_='mission')
        if mission_element:
            mission = mission_element.text.strip()
        else:
            logging.warning(f"Mission element not found for date: {date_str}")
            continue

        location_element = mission_element.find_next_sibling('div', class_='location')
        if location_element:
            location = location_element.text.strip()
        else:
            logging.warning(f"Location element not found for date: {date_str}")
            continue

        launch_datetime = datetime.combine(date_obj.date(), time_obj.time())

        launches.append({
            'datetime': launch_datetime,
            'mission': mission,
            'location': location
        })
    
    return launches

def authenticate_google():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def create_calendar(service):
    calendar = {
        'summary': 'Vandenberg Launch Schedule',
        'timeZone': 'UTC'
    }
    created_calendar = service.calendars().insert(body=calendar).execute()
    logging.info(f"Created calendar: {created_calendar['summary']}")
    return created_calendar['id']

def add_event(service, calendar_id, launch):
    event = {
        'summary': launch['mission'],
        'location': launch['location'],
        'description': 'Space launch',
        'start': {
            'dateTime': launch['datetime'].isoformat() + 'Z',
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': (launch['datetime'] + timedelta(hours=1)).isoformat() + 'Z',
            'timeZone': 'UTC',
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 10},
            ],
        },
    }

    event = service.events().insert(calendarId=calendar_id, body=event).execute()
    logging.info(f"Event created: {event.get('htmlLink')}")

def main():
    service = authenticate_google()
    calendar_id = create_calendar(service)
    launches = get_launch_schedule()

    for launch in launches:
        add_event(service, calendar_id, launch)

if __name__ == '__main__':
    main()
