import json
import pymongo
import certifi
import os
import boto3
import datetime
import requests

ca = certifi.where()
DATABASE_NAME = os.getenv("DATABASE_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
MONGODB_URL = os.getenv("MONGODB_URL")
BUCKET_NAME = os.getenv("BUCKET_NAME") 
DEFAULT_START_DATE = os.getenv("DEFAULT_START_DATE", "2026-02-09")

# ✅ FIXED: REMOVED URL WHITESPACE (critical fix - no spaces before ?)
DATA_SOURCE_URL = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/?date_received_max=<todate>&date_received_min=<fromdate>&field=all&format=json"

client = pymongo.MongoClient(MONGODB_URL, tlsCAFile=ca)
MAX_DAYS = 7 

def get_from_date_to_date():
    from_date = datetime.datetime.strptime(DEFAULT_START_DATE, "%Y-%m-%d")
    
    if COLLECTION_NAME in client[DATABASE_NAME].list_collection_names():
        res = client[DATABASE_NAME][COLLECTION_NAME].find_one(sort=[("to_date", pymongo.DESCENDING)])
        if res is not None:
            from_date = res["to_date"]
    
    to_date = datetime.datetime.now()
    
    
    max_to_date = from_date + datetime.timedelta(days=MAX_DAYS)
    if (to_date - from_date).days > MAX_DAYS:
        to_date = max_to_date
    
    return {
        "from_date": from_date.strftime("%Y-%m-%d"),
        "to_date": to_date.strftime("%Y-%m-%d"),
        "from_date_obj": from_date,
        "to_date_obj": to_date
    }

def save_from_date_to_date(data):
    client[DATABASE_NAME][COLLECTION_NAME].insert_one(data)

def lambda_handler(event, context):
    date_info = get_from_date_to_date()
    from_date = date_info["from_date"]
    to_date = date_info["to_date"]
    from_date_obj = date_info["from_date_obj"]
    to_date_obj = date_info["to_date_obj"]
    
    if to_date == from_date:
        return {'statusCode': 200, 'body': json.dumps('All data already processed')}
    
   
    url = DATA_SOURCE_URL.replace("<todate>", to_date).replace("<fromdate>", from_date)
    response = requests.get(url, headers={'User-Agent': 'etl-bot/1.0'})
    
    # Extract complaint data
    finance_complaint_data = [
        x["_source"] for x in json.loads(response.content) if "_source" in x
    ]
    
    
    s3_key = f"raw-data/{from_date.replace('-','_')}_{to_date.replace('-','_')}_finance_complaint.json"
    boto3.resource('s3').Object(BUCKET_NAME, s3_key).put(
        Body=json.dumps(finance_complaint_data).encode('UTF-8')
    )
    
   
    save_from_date_to_date({"from_date": from_date_obj, "to_date": to_date_obj})
    
    return {
        'statusCode': 200,
        'body': json.dumps(f'Processed {len(finance_complaint_data)} records')
    }