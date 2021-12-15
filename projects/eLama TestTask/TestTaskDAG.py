from airflow.models import DAG
from airflow.utils.dates import days_ago
from airflow.operators.python_operator import PythonOperator
from airflow.operators.postgres_operator import PostgresOperator
#from airflow.providers.google.cloud.operators import bigquery


import pandas as pd
import psycopg2
import csv
from google.cloud import bigquery
from google.oauth2 import service_account

args = {'start_date': days_ago(1)}

dag = DAG(
    dag_id='TestTaskDAG',
    default_args=args, 
    schedule_interval=None
    )
def create_table_load_data_from_csv():
    con = psycopg2.connect(
        database="airflow", 
        user="postgres", 
        password="password", 
        host="127.0.0.1", 
        port="5432"
    )
    create_load_users(con)
    create_load_transactions(con)
    create_load_webinar(con)
    
    con.close()

def create_load_users(con):
    cur = con.cursor()
    
    cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                user_id SERIAL NOT NULL, 
                email VARCHAR NOT NULL, 
                date_registration DATE NOT NULL);
                """)

    sqlstr = "COPY users FROM STDIN DELIMITER ',' CSV header"
    with open('/home/tk/airflow/dags/TestTaskData/users.csv') as f:
        cur.copy_expert(sqlstr, f)
    con.commit()
    
    
def create_load_transactions(con):
    cur = con.cursor()
    
    cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
            user_id SERIAL NOT NULL,
            price INTEGER NOT NULL);
            """)

    sqlstr = "COPY transactions FROM STDIN DELIMITER ',' CSV header"
    with open('/home/tk/airflow/dags/TestTaskData/transactions.csv') as f:
        cur.copy_expert(sqlstr, f)
    con.commit()
    
def create_load_webinar(con):
    cur = con.cursor()
    
    cur.execute("""
            CREATE TABLE IF NOT EXISTS webinar (
            email VARCHAR NOT NULL);
            """)
    
    sqlstr = "COPY webinar FROM STDIN DELIMITER ',' CSV header"
    with open('/home/tk/airflow/dags/TestTaskData/webinar_v2.csv') as f:
        cur.copy_expert(sqlstr, f)
    
    con.commit()

def BQ_create_table_load_data():
    
    credentials = "postgresql://postgres:password@127.0.0.1:5432/airflow"
    key_path = "/home/tk/airflow/google_key.json"
    
    dataset_name = "TestTask"
    table_name = "new_users_sum_transactions"
    
    SQL = "SELECT * FROM " + table_name
    
    df = pd.read_sql(SQL, con = credentials)
    credentials = service_account.Credentials.from_service_account_file(key_path, scopes=["https://www.googleapis.com/auth/cloud-platform"],)

    bigqueryClient = bigquery.Client(credentials=credentials, project=credentials.project_id,)
    
    table_id = credentials.project_id + "." + dataset_name + "." + table_name
    
    schema = [
        bigquery.SchemaField("email", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("sum_price", "INT64", mode="REQUIRED"),
    ]

    table = bigquery.Table(table_id, schema=schema)
    table = bigqueryClient.create_table(table)  # Make an API request.
    
    #table_ref = bigquery.dataset.table(table_name)
    #table = bigquery.Table(table_ref, schema=dataset_name)
    #table = client.create_table(table)
    
    table_ref = bigqueryClient.dataset(dataset_name).table(table_name)
    job = bigqueryClient.load_table_from_dataframe(df, table_ref)

with dag:
    
    create_table_load_data_from_csv = PythonOperator(
        task_id = 'create_table_load_data_from_csv',
        python_callable = create_table_load_data_from_csv,
    )
    
    create_materialized_view = PostgresOperator(
        task_id="create_materialized_view",
        postgres_conn_id = "postgres_default",
        sql="""
	CREATE MATERIALIZED VIEW new_users_sum_transactions
            AS
                WITH
                    new_users as(
						SELECT u.email, MIN(u.date_registration) as min_date
						FROM users u
						RIGHT JOIN webinar w ON u.email = w.email
						WHERE u.email IS NOT NULL 
						GROUP BY u.email
					),
					id_transactions_after_webinar as(
						SELECT 
    						u.user_id,
							u.email
						FROM 
							users u
						RIGHT JOIN new_users nu ON u.email = nu.email
						WHERE u.email IS NOT NULL AND nu.min_date > '2016-04-01'
					)
					
					SELECT
                        t_id.email,
                        SUM(t.price) as sum_price
                    FROM id_transactions_after_webinar t_id
                    LEFT JOIN transactions t ON t_id.user_id = t.user_id
                    GROUP BY t_id.email
          """,
    )
    

    
    BQ_create_table_load_data = PythonOperator(
        task_id = 'BQ_create_table_load_data',
        python_callable = BQ_create_table_load_data,
    )

create_table_load_data_from_csv >> create_materialized_view >> BQ_create_table_load_data