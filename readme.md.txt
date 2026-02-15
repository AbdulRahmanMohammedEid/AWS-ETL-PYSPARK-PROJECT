s3= cf-complaints-staging-data

lambda = cf-complaints-data-ingestion

glue job =cf-complaints-data-transform-job

dynamodb= cf-transformed-data

mangodb = cf-complaints-metadata

collection name = consumerdata

1-Provisioned a MongoDB Atlas cluster to persist incremental processing watermarks (`from_date`/`to_date`), establishing a durable checkpoint mechanism for fault-tolerant, resume-capable ETL orchestration.

https://account.mongodb.com/account/login

2- Installed MongoDB Compass as the graphical interface 

https://www.mongodb.com/try/download/compass

3-Established the Lambda function source directory (`lambda_function_code/`) within the project workspace and implement the core logic in `lambda_function.py`

4- This Lambda function fetches new consumer complaint data in 7-day batches by checking the last processed dates stored in MongoDB—starting from a default date if no prior run exists. It retrieves records from the CFPB API for that date range, saves the raw JSON to an S3 bucket, and updates the tracking record so the next run continues where it left off—preventing duplicate processing on restarts.

5-lambda source code 

```python
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
```

6- Install required Python packages (`pymongo`, `boto3`, `requests`) into a Lambda-compatible folder using `pip`, targeting the correct Linux platform to prevent runtime errors when deployed to AWS Lambda.

```python
pip install --platform manylinux2014_x86_64 --target=lambda_function_dep --implementation cp --python-version 3.12.2 --only-binary=:all: --upgrade pymongo boto3 requests
```

7-Created the AWS Lambda function `cf-complaints-data-ingestion` with Python 3.12 runtime and uploaded the deployment package containing the handler code and dependencies, establishing the serverless entry point for incremental data ingestion from the Consumer Financial API.

8-go to lambda cofiguration then **Environment variables and add** 

![image.png](attachment:ecd0b7cb-6900-4298-a045-a9aa021fedf3:image.png)

9- Adjusted the Lambda function’s resource configuration by increasing the timeout to 5 minutes and memory allocation to 1024 MB 

10- create s3 bucket (cf-complaints-staging-data) 

10- Creat an IAM execution role for the Lambda function with least-privilege permissions to access s3 bucket

11- Test the `cf-complaints-data-ingestion` Lambda function by verifying that it creates a `raw-data/` folder in the S3 bucket containing a JSON file with consumer complaint records and inserts a document into the MongoDB `consumerdata` collection with the processed `from_date` and `to_date`, confirming end-to-end checkpointing and data persistence.

12-Create a DynamoDB table named `cf-transformed-data` with a partition key `complaint_id` (Number) and a sort key `product` (String) to serve as the target destination for transformed consumer complaint records processed by the AWS Glue job.

13-In AWS Glue Studio, use the script editor with the Spark engine to create an ETL job named `cf-complaints-data-transform-job` that reads raw JSON complaint data from the S3 staging bucket, applies cleaning and transformation logic , and writes the structured output to the DynamoDB table `cf-transformed-data`.

14-paste the pyspark code into script editor

```python

import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as func
from awsglue.context import GlueContext
from awsglue.dynamicframe import DynamicFrame
from pyspark.sql.types import LongType
from awsglue.job import Job
import os 
## @params: [JOB_NAME]
args = getResolvedOptions(sys.argv, ['JOB_NAME'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

#declaring constant variables
BUCKET_NAME="cf-complaints-staging-data"
DYNAMODB_TABLE_NAME="cf-transformed-data"
INPUT_FILE_PATH=f"s3://{BUCKET_NAME}/raw-data/*json"

#getting logger object to log the progress
logger  = glueContext.get_logger()
logger.info(f"Started reading json file from {INPUT_FILE_PATH}")
df_sparkdf=spark.read.json(INPUT_FILE_PATH)
logger.info(f"Type casting columns of spark dataframe to Long type")
df_sparkdf = df_sparkdf.withColumn("complaint_id",func.col("complaint_id").cast(LongType()))

logger.info(f"Columns in dataframe : {len(df_sparkdf.columns)}--> {df_sparkdf.columns}")
logger.info(f"Number of rows found in file: {df_sparkdf.count()} ")

dyf = glueContext.create_dynamic_frame.from_options(
    connection_type="dynamodb",
    connection_options={"dynamodb.input.tableName": DYNAMODB_TABLE_NAME,
        "dynamodb.throughput.read.percent": "1.0",
        "dynamodb.splits": "100"
    }
)
dyf_sparkdf=dyf.toDF()
new_sparkdf=None
if dyf_sparkdf.count()!=0:
    logger.info(f"Columns in dynamodb dataframe : {len(dyf_sparkdf.columns)}--> {dyf_sparkdf.columns}")
    logger.info(f"Number of rows found in file: {dyf_sparkdf.count()} ")
    logger.info(f"Renaming exiting complaint id column of dynamodb ")
    existing_complaint_spark_df = dyf_sparkdf.select("complaint_id").withColumnRenamed("complaint_id","existing_complaint_id")
    logger.info(f"Applying left join on new dataframe from s3 and dynamo db ")
    joined_sparkdf = df_sparkdf.join(existing_complaint_spark_df,df_sparkdf.complaint_id==existing_complaint_spark_df.existing_complaint_id,"left")
    logger.info(f"Number of row after left join : {joined_sparkdf.count()}")
    new_sparkdf = joined_sparkdf.filter("existing_complaint_id is null")
    new_sparkdf.drop("existing_complaint_id")
    new_sparkdf=new_sparkdf.coalesce(10)
else:
    new_sparkdf=df_sparkdf.coalesce(10)

logger.info(f"Converting spark dataframe to DynamicFrame")
newDynamicFrame= DynamicFrame.fromDF(new_sparkdf, glueContext, "new_sparkdf")
logger.info(f"Started writing new records into dynamo db dataframe.")
logger.info(f"Number of records will be written to dynamodb: {new_sparkdf.count()}")
glueContext.write_dynamic_frame_from_options(
    frame=newDynamicFrame,
    connection_type="dynamodb",
    connection_options={"dynamodb.output.tableName": DYNAMODB_TABLE_NAME,
        "dynamodb.throughput.write.percent": "1.0"
    }
)

logger.info(f"Data has been dumped into dynamodb ")
logger.info(f"Archiving file from raw-data source: s3://{BUCKET_NAME}/raw-data  to archive: s3://{BUCKET_NAME}/archive ")
os.system(f"aws s3 sync s3://{BUCKET_NAME}/raw-data s3://{BUCKET_NAME}/archive")

logger.info(f"File is successfully archived.")
os.system(f"aws s3 rm s3://{BUCKET_NAME}/raw-data/ --recursive")
    
job.commit()
```

15- In the job details, configure an IAM role that grants AWS Glue read access to the S3 bucket containing raw complaint data and write access to the DynamoDB table `cf-transformed-data`, .

16- Save and run the `cf-complaints-data-transform-job` to validate end-to-end transformation: confirm that raw JSON files from the S3 `raw-data/` prefix are processed, loaded into the DynamoDB table `cf-transformed-data`, and subsequently moved to an `archived/` location in S3 to prevent reprocessing  

17-Configure Amazon EventBridge as a trigger for the `cf-complaints-data-ingestion` Lambda function to invoke it on a recurring schedule (e.g., daily), and enable the built-in scheduling feature in the AWS Glue job `cf-complaints-data-transform-job` to run at a later time—ensuring orchestrated, automated execution where ingestion precedes transformation in the pipeline workflow.