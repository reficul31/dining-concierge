import json
import boto3
import datetime
import dateutil.parser

slot_values = ["Location", "Cuisine", "DiningPartySize", "DiningDate", "DiningTime", "PhoneNumber"]
locations_available = ["manhattan"]
cuisines_available = ["indian", "chinese", "italian", "ethiopian", "french", "american", "mexican", "japanese", "spanish"]
string_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10, "11": 11, "12": 12, "13": 13, "14": 14, "15": 15, "16": 16, "17": 17, "18": 18, "19": 19, "20": 20}
USER_INFO_TABLE_NAME = 'user-info'

DINNER_SUGGESTION_CLOSING = "You’re all set. Expect my suggestions shortly! Have a good day."
DINNER_SUGGESTION_OLD_RECOMMENDATION_CLOSING = "You’re all set. Expect my suggestions shortly! In the meantime, here are your suggestions from last time in {} for {} food:\n{}"

slot_configuration = {
    "Location": {
        'querySlot': "Great! I can help you with that. What city or city area are you looking to dine in?",
        'queryError': "I'm sorry, we only support the following locations: {}. Please choose from them.".format(", ".join(locations_available)),
        'validate': lambda location: validate_location(location),
        'converter': None
    },
    "Cuisine": {
        'querySlot': "Got it! What cuisine would you like to try?",
        'queryError': "I'm sorry we don't support that cuisine. Please choose one of the following cuisines: {}.".format(", ".join(cuisines_available)),
        'validate': lambda cuisine: validate_cuisine(cuisine),
        'converter': None
    },
    "DiningPartySize": {
        'querySlot': "Ok, how many people are in your party?",
        'queryError': "We don't support that number of people. Please input a number between 1 and 20",
        'validate': lambda party: validate_party_size(party),
        'converter': lambda party: string_to_num[party]
    }, 
    "DiningDate": {
        'querySlot': "A few more to go. What date?",
        'queryError': "That is not a valid date. Please try and input a date from today onwards.",
        'validate': lambda date: validate_date(date),
        'converter': None
    },
    "DiningTime": {
        'querySlot': "What time?",
        'queryError': "That is not a valid time. Please try again.",
        'validate': lambda time: validate_time(time),
        'converter': None
    },
    "PhoneNumber": {
        'querySlot': "Great. Lastly, I need your phone number so I can send you my findings.",
        'queryError': "Please input a valid US number. Make sure there are no hyphens or extensions such as +1 added.",
        'validate': lambda number: validate_number(number),
        'converter': None
    }
}

def validate_location(location):
    return location.lower() in locations_available

def validate_cuisine(cuisine):
    return cuisine.lower() in cuisines_available

def validate_party_size(party):
    return party.lower() in list(string_to_num.keys())

def validate_number(number):
    return len(number) == 10 and number.isnumeric()

def validate_time(time):
    try:
        parsed_time = dateutil.parser.parse(time).timestamp()
        return True
    except ValueError:
        return False;

def validate_date(date):
    try:
        parsed_date = dateutil.parser.parse(date).date()
        return parsed_date >= datetime.date.today()
    except ValueError:
        return False

def build_response(event, content, dialogActionType='Close', fulfillmentState='Fulfilled', contentType='PlainText'):
    session_attributes = event['sessionAttributes'] if event['sessionAttributes'] is not None else {}
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': dialogActionType,
            'fulfillmentState': fulfillmentState,
            'message': {
                'contentType': contentType,
                'content': content
            }
        }
    }

def elicit_slot(event, message, slots, slotToElicit):
    response = build_response(event, message, dialogActionType='ElicitSlot')
    response['dialogAction'].pop('fulfillmentState', None)
    response['dialogAction']['intentName'] = 'DiningSuggestionsIntent'
    
    response['dialogAction']['slots'] = slots
    response['dialogAction']['slotToElicit'] = slotToElicit
    return response

def delegate_slot(event, slots):
    response = build_response(event, "", dialogActionType='Delegate')
    response['dialogAction'].pop('fulfillmentState', None)
    response['dialogAction'].pop('message', None)
    response['dialogAction']['slots'] = slots
    return response

def handleGreetingIntent(event):
    return build_response(event, "Hello there, how can I help you?")

def handleThankYouIntent(event):
    return build_response(event, "Thank you for using the Dining Concierge service.")

def handleNoIntent(event):
    return build_response(event, "Failed to recognize the intent.", fulfillmentState='Failed')

def get_old_recommendations(phone):
    client = boto3.resource('dynamodb')
    table = client.Table(USER_INFO_TABLE_NAME)
    
    print("Getting ID: {}".format(id))
    response = table.get_item(Key={'phone': phone})
    if 'Item' not in response:
        print('User not yet present in the sessions database')
        return None
    
    suggestion = response['Item']
    return {
        'phone': suggestion['phone'],
        'cuisine': suggestion['cuisine'],
        'location': suggestion['location'],
        'message': suggestion['message']
    }
    
def handleDiningSuggestionsIntent(event):
    reservation_request = dict.fromkeys(slot_values)
    
    slots = event['currentIntent']['slots']
    for slot in slot_values:
        slot_value = slots.get(slot)
        if slot_value is None:
            return delegate_slot(
                event,
                reservation_request
            )
        elif not slot_configuration[slot]['validate'](slot_value):
            return elicit_slot(
                event, 
                slot_configuration[slot]['queryError'], 
                reservation_request,
                slot
            )
        else:
            if slot_configuration[slot]['converter'] is not None:
                reservation_request[slot] = slot_configuration[slot]['converter'](slot_value)
            else:
                reservation_request[slot] = slot_value
    
    queue_msg_sqs(reservation_request)
    
    old_suggestion = get_old_recommendations(reservation_request['PhoneNumber'])
    if old_suggestion is not None:
        return build_response(
            event,
            DINNER_SUGGESTION_OLD_RECOMMENDATION_CLOSING.format(
                old_suggestion['location'],
                old_suggestion['cuisine'],
                old_suggestion['message'])
        )
    return build_response(event, DINNER_SUGGESTION_CLOSING)

def queue_msg_sqs(reservation_request):
    client = boto3.client('sqs')
    url = client.get_queue_url(QueueName="DiningConciergeQueue")['QueueUrl']
    
    try:
        response = client.send_message(QueueUrl=url, MessageBody=json.dumps(reservation_request))
        print("SQS Response: {}".format(response))
    except ClientError as e:
        print("SQS Error: {}".format(e))

def lambda_handler(event, context):
    print("Event: {}".format(event))
    
    intent_name = event['currentIntent']['name']
    if intent_name == 'GreetingIntent':
        return handleGreetingIntent(event)
    elif intent_name == 'ThankYouIntent':
        return handleThankYouIntent(event)
    elif intent_name == 'DiningSuggestionsIntent':
        return handleDiningSuggestionsIntent(event)
    else:
        return handleNoIntent(event)
