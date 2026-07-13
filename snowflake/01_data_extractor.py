import snowflake.connector

from snowflake.connector.pandas_tools import write_pandas
from snowflake.connector.cursor import DictCursor


conn = snowflake.connector.connect(
    user="LAKSHYA2992",
    password="XYZ",
    account="AYYGNWS-SV86376",
    warehouse="COMPUTE_WH",
    database="AI_DB",
    schema="PUBLIC"
)

cursor = conn.cursor(DictCursor)

cursor.execute("""
SELECT *
FROM INCIDENTS
""")

rows = cursor.fetchall()

print(rows[0])