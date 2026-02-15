

---

# Project Resources

- **S3 Bucket**: `cf-complaints-staging-data`  
- **Lambda Function**: `cf-complaints-data-ingestion`  
- **Glue Job**: `cf-complaints-data-transform-job`  
- **DynamoDB Table**: `cf-transformed-data`  
- **MongoDB Database**: `cf-complaints-metadata`  
- **MongoDB Collection**: `consumerdata`

---

## Setup Steps

1. **Provisioned a MongoDB Atlas cluster** to persist incremental processing watermarks (`from_date`/`to_date`), establishing a durable checkpoint mechanism for fault-tolerant, resume-capable ETL orchestration.  
   [https://account.mongodb.com/account/login](https://account.mongodb.com/account/login)

2. **Installed MongoDB Compass** as the graphical interface.  
   [https://www.mongodb.com/try/download/compass](https://www.mongodb.com/try/download/compass)

3. **Establish  Lambda function source directory** (`lambda_function_code/`) within the project workspace and implement the core logic in `lambda_function.py`.

4. **This Lambda function fetches new consumer complaint data in 7-day batches** by checking the last processed dates stored in MongoDB—starting from a default date if no prior run exists. It retrieves records from the CFPB API for that date range, saves the raw JSON to an S3 bucket, and updates the tracking record so the next run continues where it left off—preventing duplicate processing on restarts.

5. Note: Go to MongoDB Atlas IP Access List and add 0.0.0.0/0 to allow connections from any IP address (for practice purposes only—not recommended for production).

6. **Install required Python packages** (`pymongo`, `boto3`, `requests`) into a Lambda-compatible folder using `pip`, targeting the correct Linux platform to prevent runtime errors when deployed to AWS Lambda.

```bash
pip install --platform manylinux2014_x86_64 --target=lambda_function_dep --implementation cp --python-version 3.12.2 --only-binary=:all: --upgrade pymongo boto3 requests
```

7. **Creat AWS Lambda function** `cf-complaints-data-ingestion` with Python 3.12 runtime and uploaded the zip file  containing the  code and dependencies.

8. **Go to Lambda configuration → Environment variables and add**  
   <img width="1192" height="388" alt="Image" src="https://github.com/user-attachments/assets/07c25221-e683-401d-a9ca-f8f46284b011" />

9. **Adjusted the Lambda function’s resource configuration** by increasing the timeout to 5 minutes and memory allocation to 1024 MB.

10. **Create S3 bucket**: `cf-complaints-staging-data`.

11. **Create an IAM execution role for the Lambda function** with least-privilege permissions to access S3 bucket.

12. **Test the `cf-complaints-data-ingestion` Lambda function** by verifying that it creates a `raw-data/` folder in the S3 bucket containing a JSON file with consumer complaint records and inserts a document into the MongoDB `consumerdata` collection with the processed `from_date` and `to_date`, confirming end-to-end checkpointing and data persistence.

13. **Create a DynamoDB table** named `cf-transformed-data` with a partition key `complaint_id` (Number) and a sort key `product` (String) to serve as the target destination for transformed consumer complaint records processed by the AWS Glue job.

14. **In AWS Glue Studio, use the script editor with the Spark engine** to create an ETL job named `cf-complaints-data-transform-job` that reads raw JSON complaint data from the S3 staging bucket, applies cleaning and transformation logic, and writes the structured output to the DynamoDB table `cf-transformed-data`.

15. **Paste the PySpark code into script editor**

16. **In the job details, configure an IAM role** that grants AWS Glue read access to the S3 bucket containing raw complaint data and write access to the DynamoDB table `cf-transformed-data`.

17. **Save and run the `cf-complaints-data-transform-job`** to validate end-to-end transformation: confirm that raw JSON files from the S3 `raw-data/` prefix are processed, loaded into the DynamoDB table `cf-transformed-data`, and subsequently moved to an `archived/` location in S3 to prevent reprocessing.

18. **Configure Amazon EventBridge as a trigger** for the `cf-complaints-data-ingestion` Lambda function to invoke it on a recurring schedule (e.g., daily), and enable the built-in scheduling feature in the AWS Glue job `cf-complaints-data-transform-job` to run at a later time—ensuring orchestrated, automated execution where ingestion precedes transformation in the pipeline workflow.

--- 

