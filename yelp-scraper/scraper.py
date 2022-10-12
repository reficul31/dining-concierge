import sys
import json
import json
import boto3
import string
import requests
import datetime

from urllib.error import HTTPError
from urllib.parse import quote

CUISINES = ["indian", "chinese", "italian", "ethiopian", "french", "american", "mexican", "japanese", "spanish"]
LOCATION = 'Manhattan, NY'
SEARCH_LIMIT = 50

API_KEY = ''
API_HOST = 'https://api.yelp.com'
SEARCH_PATH = '/v3/businesses/search'

KEY_ID = ''
ACCESS_KEY = ''
TABLE_NAME = 'yelp-restaurants'

def get_proper_name(restaurant_name):
    printable = set(string.printable)
    english_name = ''.join(filter(lambda x: x in printable, restaurant_name))
    return english_name

def get_businesses_from_API(term, offset):
    url_params = {
        'term': "{} restaurant".format(term).replace(' ', '+'),
        'location': LOCATION.replace(' ', '+'),
        'limit': SEARCH_LIMIT,
        'offset': offset
    }
    url_params = url_params or {}
    url = '{0}{1}'.format(API_HOST, quote(SEARCH_PATH.encode('utf8')))
    headers = {
        'Authorization': 'Bearer %s' % API_KEY,
    }
    response = requests.request('GET', url, headers=headers, params=url_params)
    return response.json()

def get_all_businesses(term):
    offset, cuisine_restaurants = 0, []
    total = None
    while total is None or len(cuisine_restaurants) <= total:
        response = get_businesses_from_API(term, offset)
        restaurants = response.get('businesses', None)
        
        if total is None:
            total = min(response.get('total', 1000), 1000)
        
        if restaurants is None or len(restaurants) == 0:
            print("Restaurants were returned as None")
            break
        
        cuisine_restaurants = cuisine_restaurants + restaurants
        offset += SEARCH_LIMIT
        print("{}/{} - {} Restaurants Fetched".format(len(cuisine_restaurants), total, term))
    return cuisine_restaurants

if __name__ == '__main__':
    try:
        for cuisine in CUISINES:
            cuisine_restaurants = get_all_businesses(cuisine)
            with open("{}_data.json".format(cuisine), "w") as f:
                json.dump(cuisine_restaurants, f)
            print("{}:{} entries".format(cuisine, len(cuisine_restaurants)))

    except HTTPError as error:
        sys.exit(
            'Encountered HTTP error {0} on {1}:\n {2}\nAbort program.'.format(
                error.code,
                error.url,
                error.read(),
            )
        )
    
    client = boto3.resource('dynamodb', region_name='us-east-1', aws_access_key_id=KEY_ID, aws_secret_access_key=ACCESS_KEY)
    db = client.Table(TABLE_NAME)
    
    for cuisine in CUISINES:
        with open('{}_data.json'.format(cuisine), 'r') as f:
            restaurants = json.load(f)

            for index, restaurant in enumerate(restaurants):
                print('{}/{} {} restaurant put in the DB'.format(index, len(restaurants), cuisine))
                data = {
                    'Id': restaurant.get('id'),
                    'cuisine': cuisine,
                    'name': get_proper_name(restaurant.get('name', None)),
                    'rating': int(restaurant.get('rating', 0)),
                    'review_count': int(restaurant.get('review_count', 0)),
                    'address': str(" ".join(restaurant['location'].get('display_address', []))),
                    'zip_code': restaurant['location'].get('zip_code', None),
                    'is_closed': restaurant.get('is_closed', True),
                    'phone': restaurant.get('phone', None),
                    'image_url': restaurant.get('image_url', ''),
                    'insertedAtTimestamp': datetime.datetime.now().strftime("%m/%d/%Y, %H:%M:%S.%f")
                }

                if restaurant['coordinates']:
                    data['latitude'] = str(restaurant['coordinates']['latitude'])
                    data['longitude'] = str(restaurant['coordinates']['longitude'])
                
                db.put_item(Item=data)
