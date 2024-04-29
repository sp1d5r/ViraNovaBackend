import pandas as pd
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from database.database_interface import (
    DatabaseInterface,
    DatabaseConnectionError,
)
from database.production_db.database import engine, SessionLocal

load_dotenv()


class ProductionDatabase(DatabaseInterface):
    def __init__(self):
        """
        Initialise a connection to the production database, allows access to
        """
        try:
            self.engine = engine
            self.session = SessionLocal()
        except SQLAlchemyError as e:
            raise DatabaseConnectionError(
                f"Error occurred while creating the database engine: {e}"
            )

    def connect(self) -> None:
        try:
            self.session = sessionmaker(bind=self.engine)()
        except SQLAlchemyError as e:
            print(f"Error occurred during database connection: {e}")
            raise DatabaseConnectionError(
                f"Error occurred during database connection: {e}"
            )

    def read_table(self, table_name: str) -> pd.DataFrame:
        try:
            table_data = pd.read_sql_table(table_name, self.engine)
            return table_data
        except SQLAlchemyError as e:
            raise DatabaseConnectionError(
                f"Error occurred while reading table {table_name}: {e}"
            )

    def write_to_table(self, data: pd.DataFrame, table_name: str) -> pd.DataFrame:
        try:
            data.to_sql(table_name, self.engine, if_exists="replace", index=False)
            return self.read_table(table_name)
        except SQLAlchemyError as e:
            raise DatabaseConnectionError(
                f"Error occurred while writing to table {table_name}: {e}"
            )

    def table_exists(self, table_name: str) -> bool:
        # Check if the table exists in the database
        inspector = inspect(self.engine)
        return table_name in inspector.get_table_names()

    def append_rows(self, data: pd.DataFrame, table_name: str) -> bool:
        try:
            # Directly attempt to append data to the table
            data.to_sql(table_name, self.engine, if_exists="append", index=False)
            return True
        except SQLAlchemyError as e:
            # Catch any SQLAlchemy errors that occur during the append operation
            raise DatabaseConnectionError(
                f"Error occurred while appending data to table {table_name}: {e}"
            )

    def upsert_rows(self, data: pd.DataFrame, table_name: str, primary_key: str) -> bool:
        try:
            # Start a transaction
            self.session.begin()

            primary_keys = data[
                primary_key
            ].unique()  # Get unique primary keys from DataFrame

            # Delete existing records in bulk
            delete_stmt = f"DELETE FROM {table_name} WHERE {primary_key} IN :primary_keys"
            self.session.execute(text(delete_stmt), {"primary_keys": tuple(primary_keys)})

            self.session.commit()

            # Append new rows
            success = self.append_rows(data, table_name)
            if not success:
                raise Exception("Failed to append rows")

            return True
        except SQLAlchemyError as e:
            self.session.rollback()
            raise DatabaseConnectionError(
                f"Error occurred while upserting data to table {table_name}: {e}"
            )

    def query_table_by_column(self, table_name: str, column_name: str, column_value: any) -> pd.DataFrame:
        """
        Query rows from the specified table where the specified column matches the given value.

        Args:
        - table_name (str): The name of the table to query.
        - column_name (str): The name of the column to filter on.
        - column_value (any): The value to match in the specified column.

        Returns:
        - pd.DataFrame: A DataFrame containing the rows from the database where the column values match.

        Raises:
        - DatabaseConnectionError: If any error occurs during the database operation.
        """
        try:
            query = text(f"SELECT * FROM {table_name} WHERE {column_name} = :column_value")
            result = self.session.execute(query, {'column_value': column_value})
            transcripts = pd.DataFrame(result.fetchall(), columns=result.keys())
            return transcripts
        except SQLAlchemyError as e:
            raise DatabaseConnectionError(
                f"Error occurred while querying {table_name} for {column_name} = {column_value}: {e}"
            )

