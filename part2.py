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

#File to save last update time, will move this to S3 later
last_update = "last_update-p1"
raw_out_loc = "file:///home/msr/case-study/raw/"
bucket_name = "rcs-training-12-18"
files = ["promotion", "store", "sales_fact_1997", "sales_fact_1998", "sales_fact_dec_1998", "time_by_day"]

sc = SparkContext("local[2]", "Case-Study-Part-1")
sqlContext = SQLContext(sc)
spark = SparkSession.builder.appName("Case-Study-Part-2").getOrCreate()

# Just to show the each section of the program in the middle of all the output
def section_header(h):
    print "\n\n\n"
    print "----------"+h+"----------"
    print "\n\n\n"


# Writes the dataframe to S3 using boto3
# Saves the data as an avro
def read_avro_from_s3():
    s3 = boto3.resource('s3')
    dfs = []
    already_read = []
    bucket = s3.Bucket(bucket_name)
    for obj in bucket.objects.all():
        key = obj.key
        key_parts = key.split("/")
        if key_parts[1] in files and key_parts[0] == "raw":
            f = tempfile.NamedTemporaryFile(delete=False)
            f.write(obj.get()['Body'].read())
            f.close()
            data = spark.read.format("avro").load(f.name)
            if key_parts[1] in already_read:
                idx = already_read.index(key_parts[1])
                dfs[idx] = (dfs[idx]).union(data)
            else:
                dfs.append(data)
                already_read.append(str(key_parts[1]))
    return dfs, already_read


# Removes all non-sale promotions from all sales tables by filtering by promotion ID
def remove_non_prom_sales(dfs, t_order):
    section_header("Removing non-promotion sales")
    for i in range(len(dfs)):
        if t_order[i].startswith("sales"):
            dfs[i] = dfs[i].filter(col('promotion_id') != 0)
    return dfs


# Writes the dataframe to S3 using boto3
# Saves the data as a parquet
def write_parquet2s3(df, dir_name, write_time):
    client = boto3.client('s3')
    path = os.path.join(tempfile.mkdtemp(), dir_name)
    df.write.format("parquet").save(path)
    for f in os.listdir(path):
        if f.startswith('part'):
            out = path + "/" + f
    client.put_object(Bucket=bucket_name, Key="cleansed/" + dir_name + "/" + write_time + ".parquet",
                      Body=open(out, 'r'))


# Joins the sales tables and updates the dfs array
def join_sales(dfs, t_order):
    section_header("Join Sales")
    new_dfs = []
    table_order = []
    sales_tables = []
    for i in range(len(dfs)):
        if t_order[i].startswith("sales"):
            sales_tables.append(i)
        else:
            new_dfs.append(dfs[i])
            table_order.append(t_order[i])
    new_dfs.append(dfs[sales_tables[0]])
    for i in range(len(sales_tables)):
        if i != 0:
            new_dfs[len(new_dfs)-1] = new_dfs[len(new_dfs)-1].union(dfs[sales_tables[i]])
    table_order.append("sales")
    return new_dfs, table_order


def main(arg):
    section_header("Get avro files from S3")
    dfs, table_order = read_avro_from_s3()
    dfs = remove_non_prom_sales(dfs, table_order)
    dfs, table_order = join_sales(dfs, table_order)
    write_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    section_header("Writing Parquet to S3")
    for i in range((len(dfs))):
        write_parquet2s3(dfs[i], table_order[i], write_time)


# Runs the script
if __name__ == "__main__":
    section_header("Program Start")
    main(sys.argv[1:])