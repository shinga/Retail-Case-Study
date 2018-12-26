# Run script with full load:
# spark-submit --packages mysql:mysql-connector-java:5.1.39,org.apache.spark:spark-avro_2.11:2.4.0 part1.py F
# To run the script with S3 pushing run
# spark-submit --packages mysql:mysql-connector-java:5.1.39,org.apache.spark:spark-avro_2.11:2.4.0 part1.py F s3

# Run script with incremental load:
# spark-submit --packages mysql:mysql-connector-java:5.1.39,org.apache.spark:spark-avro_2.11:2.4.0 part1.py I
# To run the script with S3 pushing run
# spark-submit --packages mysql:mysql-connector-java:5.1.39,org.apache.spark:spark-avro_2.11:2.4.0 part1.py I s3

from pyspark import SparkContext
from pyspark.streaming import StreamingContext
from pyspark.sql import SparkSession, SQLContext
import datetime
import time
import sys
import boto3
import os
import tempfile
from pyspark.sql.functions import col


bucket_name = "rcs-training-12-18"
sc = SparkContext("local[2]", "Case-Study-Part-3")
sqlContext = SQLContext(sc)
spark = SparkSession.builder.appName("Case-Study-Part-3").getOrCreate()


# Just to show the each section of the program in the middle of all the output
def section_header(h):
    print "\n\n\n"
    print "----------"+h+"----------"
    print "\n\n\n"


# Reads the dataframes from S3 using boto3
# Data is stored as parquet before being read in
def read_parquet_from_s3():
    section_header("Get parquet files from S3")
    s3 = boto3.resource('s3')
    dfs = []
    already_read = []
    bucket = s3.Bucket(bucket_name)
    for obj in bucket.objects.all():
        key = obj.key
        key_parts = key.split("/")
        if key_parts[0] == "cleansed":
            f = tempfile.NamedTemporaryFile(delete=False)
            f.write(obj.get()['Body'].read())
            f.close()
            data = spark.read.format("parquet").load(f.name)
            if key_parts[1] in already_read:
                idx = already_read.index(key_parts[1])
                dfs[idx] = (dfs[idx]).union(data)
            else:
                dfs.append(data)
                already_read.append(str(key_parts[1]))
    return dfs, already_read


# Writes the dataframe to S3 using boto3
# Saves the data as a csv
def write_csv2s3(dfs, table_order):
    section_header("Writing CSV to S3")
    client = boto3.client('s3')
    write_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    for i in range(len(dfs)):
        df = dfs[i]
        dir_name = table_order[i]
        path = os.path.join(tempfile.mkdtemp(), dir_name)
        df.write.format("csv").save(path)
        for f in os.listdir(path):
            if f.startswith('part'):
                out = path + "/" + f
        client.put_object(Bucket=bucket_name, Key="staging/" + dir_name + "/" + write_time + ".csv",
                          Body=open(out, 'r'))


def main(arg):
    dfs, table_order = read_avro_from_s3()
    write_csv2s3(dfs, table_order)


# Runs the script
if __name__ == "__main__":
    section_header("Program Start")
    main(sys.argv[1:])