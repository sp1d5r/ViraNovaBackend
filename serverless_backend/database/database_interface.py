from abc import ABC, abstractmethod
import pandas as pd


class DatabaseInterface(ABC):
    """
    Abstract Database Interface,

    """

    @abstractmethod
    def connect(self):
        """
        Initiate a connection to the database requested
        """
        return NotImplemented

    @abstractmethod
    def read_table(self, table_name: str) -> pd.DataFrame:
        """
        Reads the table name described below, returns a pandas dataframe
        """
        return NotImplemented

    @abstractmethod
    def write_to_table(self, data: pd.DataFrame, table_name: str) -> bool:
        return NotImplemented

    @abstractmethod
    def table_exists(self, table_name: str) -> bool:
        """
        Checks if a table exists in the database with the given name
        """
        pass

    @abstractmethod
    def append_rows(self, data: pd.DataFrame, table_name: str) -> bool:
        """
        Appends rows to an existing table. This method should include a schema check to ensure
        that the data being appended matches the schema of the table.
        """
        pass

    @abstractmethod
    def upsert_rows(self, data: pd.DataFrame, table_name: str, primary_key: str) -> bool:
        """
        Upserts rows into a table based on the primary key. If a row with the given primary key already exists,
        it updates the row with the new values. If it does not exist, it inserts a new row.

        :param data: DataFrame containing the data to upsert.
        :param table_name: The name of the table to upsert data into.
        :param primary_key: The primary key column of the table against which to check for existing records.
        :return: True if the operation is successful, otherwise raises an error.
        """
        pass

    @abstractmethod
    def query_table_by_column(self, table_name: str, column_name: str, column_value: any) -> pd.DataFrame:
        """
        Query rows from the specified table where the specified column matches the given value.

        :param table_name: (str) The name of the table to query.
        :param column_name: (str) The name of the column to filter on.
        :param column_value: (any) The value to match in the specified column.
        :return pd.DataFrame: A DataFrame containing the rows from the database where the column values match.

        Raises:
        - DatabaseConnectionError: If any error occurs during the database operation.
        """
        pass


class DatabaseConnectionError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class DatabaseSchemaException(Exception):
    """
    Exception raised for errors in the database schema, such as mismatched schema during data appending.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class DatabaseTableExistsException(Exception):
    """
    Exception raised for errors in table operations, such as write_to_table if the table doesn't exist.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
