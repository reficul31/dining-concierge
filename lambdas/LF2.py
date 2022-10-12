import json
import boto3
import requests
import random as rd

AWSAUTH = ('', '')
HEADERS = { "Content-Type": "application/json" }
OPEN_SERVICE_URL = ''
SLOT_VALUES = ["Location", "Cuisine", "DiningPartySize", "DiningDate", "DiningTime", "PhoneNumber"]
SQS_QUEUE_NAME = 'DiningConciergeQueue'
RESTAURANT_TABLE_NAME = 'yelp-restaurants'
USER_INFO_TABLE_NAME = 'user-info'
NUMBER_OF_RECOMMENDATIONS = 3
SOURCE_MAIL = ''
PHONE_TO_EMAIL = {}

MESSAGE_TEMPLATE_HEADER = "Hello! Here are my {} restaurant suggestions for {} people, for {} at {}:" 
MESSAGE_TEMPLATE_RESTAURANT = "{}. {}, located at {},"
MESSAGE_TEMPLATE_FOOTER = "Enjoy your meal!"

def get_queue_messages():
    print("Getting messages from Queue")
    client = boto3.client('sqs')
    url = client.get_queue_url(QueueName=SQS_QUEUE_NAME)['QueueUrl']
    response = client.receive_message(
        QueueUrl=url,
        AttributeNames=['All'],
        MessageAttributeNames=SLOT_VALUES,
        MaxNumberOfMessages=1,
        VisibilityTimeout=1,
        WaitTimeSeconds=1
    )
    
    if 'Messages' not in response:
        return []
    
    reservations = []
    for message in response['Messages']:
        body = json.loads(message['Body'])
        reservation = {slot: body[slot] for slot in SLOT_VALUES}
        reservation['ReceiptHandle'] = message['ReceiptHandle']
        reservations.append(reservation)
    return reservations

def remove_queue_messages(reservations):
    print("Deleting messages from Queue")
    client = boto3.client('sqs')
    url = client.get_queue_url(QueueName=SQS_QUEUE_NAME)['QueueUrl']
    for reservation in reservations:
        response = client.delete_message(
            QueueUrl=url,
            ReceiptHandle=reservation['ReceiptHandle']
        )

def get_restaurant_recommendations(cuisine):
    response = requests.get(OPEN_SERVICE_URL.format(cuisine), auth=AWSAUTH, headers=HEADERS)
    response = response.json()
    
    samples = None
    if len(response['hits']['hits']) <= NUMBER_OF_RECOMMENDATIONS:
        print("Restaurant of type {} has less than {} restaurants in them".format(cuisine, NUMBER_OF_RECOMMENDATIONS))
        samples = response['hits']['hits']
    else:
        samples = rd.sample(response['hits']['hits'], NUMBER_OF_RECOMMENDATIONS)
    return [{
        'id': sample['_source']['id'],
        'cuisine': sample['_source']['cuisine']
    } for sample in samples]

def get_restaurant_info(id, cuisine):
    client = boto3.resource('dynamodb')
    table = client.Table(RESTAURANT_TABLE_NAME)
    
    print("Getting ID: {}".format(id))
    response = table.get_item(Key={'Id': id, 'cuisine': cuisine})
    if 'Item' not in response:
        print('Item not found in the database')
        return None
    
    restaurant = response['Item']
    return {
        'Id': restaurant['Id'],
        'cuisine': restaurant['cuisine'],
        'name': restaurant['name'],
        'rating': restaurant['rating'],
        'review_count': restaurant['review_count'],
        'address': restaurant['address'],
        'zip_code': restaurant['zip_code'],
        'is_closed': restaurant['is_closed'],
        'phone': restaurant['phone']
    }

def send_message_through_ses(phone, message):
    if phone not in PHONE_TO_EMAIL.keys():
        print("Don't have the number mapped to an email address")
        return
    
    print("Sending the following message to: {}".format(PHONE_TO_EMAIL[phone]))
    print("Message: {}".format(message))
        
    client = boto3.client('ses', region_name='us-east-1')
    response = client.send_email(
        Source=SOURCE_MAIL,
        SourceArn='{}'.format(SOURCE_MAIL),
        Destination={
            'ToAddresses': [PHONE_TO_EMAIL[phone]],
            'CcAddresses': [],
            'BccAddresses': []
        },
        Message={
            'Subject': {
                'Data': 'Dining Concierge Suggestions',
                'Charset': 'UTF-8'
            },
            'Body': {
                'Text': {
                    'Data': message,
                    'Charset': 'UTF-8'
                }
            }
        }
    )

def save_user_history(phone, cuisine, location, message):
    client = boto3.resource('dynamodb')
    table = client.Table(USER_INFO_TABLE_NAME)
    suggestions = message[1:len(message)-1]
    data = {
        'phone': phone,
        'cuisine': cuisine,
        'location': location,
        'message': " ".join(suggestions)
    }
    table.put_item(Item=data)
    print("Added: {}".format(data))
    
def lambda_handler(event, context):
    reservations = get_queue_messages()
    print("Reservations:", reservations)
    for reservation in reservations:
        constructed_message = [MESSAGE_TEMPLATE_HEADER.format(reservation['Cuisine'], reservation['DiningPartySize'], reservation['DiningDate'], reservation['DiningTime'])]
        recommendations = get_restaurant_recommendations(reservation['Cuisine'])
        print("Recommendations: ", recommendations)
        for index, recommendation in enumerate(recommendations):
            restaurant = get_restaurant_info(recommendation['id'], recommendation['cuisine'])
            if restaurant is None:
                continue
            constructed_message.append(MESSAGE_TEMPLATE_RESTAURANT.format(index+1, restaurant['name'], restaurant['address']))
        constructed_message.append(MESSAGE_TEMPLATE_FOOTER)
        send_message_through_ses(reservation['PhoneNumber'], " ".join(constructed_message))
        save_user_history(reservation['PhoneNumber'], reservation['Cuisine'], reservation['Location'], constructed_message)
    remove_queue_messages(reservations)