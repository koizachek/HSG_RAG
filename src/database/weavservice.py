import weaviate as wvt
import argparse, datetime

from time import perf_counter
from weaviate.classes.config import Configure, Property, DataType
from weaviate.collections.classes.grpc import MetadataQuery
from weaviate.collections.collection import Collection

from src.utils.logging import get_logger
from config import WEAVIATE_BACKUP_BACKEND, WEAVIATE_COLLECTION_BASENAME, AVAILABLE_LANGUAGES

logger = get_logger("weaviate_service")

_get_collection_name = lambda lang: f'{WEAVIATE_COLLECTION_BASENAME}_{lang}'
_collection_names = [_get_collection_name(lang) for lang in AVAILABLE_LANGUAGES]


class WeaviateService:
    """
    Provides an interface for interacting with a local Weaviate vector database.
    Handles initialization, data import, and hybrid queries.
    """
    def __init__(self) -> None:
        """
        Initialize the Weaviate service and establish a connection to the local database.

        Raises:
            weaviate.exceptions.WeaviateConnectionError: If the connection fails.
        """
        self._client: wvt.WeaviateClient = None 
 

    def _with_connection(func):
        def wrapper(self, *args, **kwargs):
            try:
                if not self._client:
                    self._client = wvt.connect_to_local()
                if not self._client.is_connected():
                    self._client.connect()
                logger.info("Created a connection with the local weaviate database")
                result = func(self, *args, **kwargs)
                self._client.close()
                logger.info("Closed the connection with the local weaviate database")
                return result
            except Exception as e:
                logger.exception(f"Failed to connect to the local weaviate database: {e}")
           
        return wrapper


    def _select_collection(self, lang: str) -> tuple[Collection, str]:
        """
        Select a language-specific collection as the active working collection.

        Args:
            lang (str): Acceptable language code.

        Raises:
            weaviate.exceptions.WeaviateConnectionError: If the specified language collection does not exist.
        """
        if lang not  in AVAILABLE_LANGUAGES:
            logger.error(f"No collection for language '{lang}' was found in the database")
            return None, ''

        collection_name = _get_collection_name(lang)
        return self._client.collections.use(collection_name), collection_name

    @_with_connection
    def batch_import(self, data_rows: list, lang: str) -> list:
        """
        Perform a batch import of multiple objects into the current collection.

        Args:
            data_rows (list): List of dictionaries representing the data rows to import.
            lang (str, optional): Language collection to use. If not provided, uses the current one.

        Returns:
            list[dict]: List of failed imports with error details, if any.

        Raises:
            weaviate.exceptions.WeaviateConnectionError: If no active collection is available.
        """
        collection, collection_name = self._select_collection(lang)
        if not collection:
            logger.error("No working collection selected upon starting batch import!")
            return []

        import_errors = []
        logger.info(f"Initiating batch import for {len(data_rows)} data rows into collection {collection_name}")
        with collection.batch.fixed_size(batch_size=100, concurrent_requests=2) as batch:
            for idx, data_row in enumerate(data_rows):
                try:
                    batch.add_object(properties=data_row)
                except Exception as e:
                    import_errors.append({'index': idx, 'chunk_id': data_row['chunk_id'], 'error': str(e)})
                    continue
                
                # Periodical checks for failed imports
                if idx % 20 == 0 and idx > 0:
                    if batch.number_errors > 0:
                        logger.info(f"Amount of failed imports at index {idx}: {batch.number_errors}")
                        last_failed_object = self._current_collection.batch.failed_objects[-1]
                        logger.info(f"Last failure: {last_failed_object.message}")
        
        logger.info(f"Batch import finished for {collection_name}")
        logger.info("Total import errors: {len(import_errors)}" if import_errors else "No errors catched during importing!")
      
        return import_errors
   

    @_with_connection 
    def query(self, query: str, lang: str, query_properties: list[str] = None, limit: int = 5, distance: float = 0.25) -> dict:
        """
        Execute a hybrid semantic and keyword query against the active collection.

        Args:
            query (str): The query string.
            query_properties (list[str], optional): List of properties to query against.
            limit (int, optional): Maximum number of results to return. Defaults to 5.
            distance (float, optional): Distance threshold for the query. Defaults to 0.25.
            lang (str, optional): Language collection to use. If not provided, uses the current one.

        Returns:
            tuple: A tuple containing the query response and elapsed time.

        Raises:
            weaviate.exceptions.WeaviateConnectionError: If no active collection is available.
        """ 
        collection, collection_name = self._select_collection(lang)
        if not collection:
            logger.error("No working collection selected upon starting of the querying!")
            return []
        
        logger.info(f"Querying collection {collection_name}")
        query_start_time = perf_counter()
        resp = collection.query.hybrid(
            query=query,
            query_properties=query_properties,
            distance=distance,
            limit=limit,
            return_metadata=MetadataQuery.full()
        )
        elapsed = perf_counter() - query_start_time
        logger.info(f"Querying retrieved {len(resp.objects)} objects in {elapsed} seconds")

        return (resp, elapsed)


    @_with_connection
    def _create_collections(self):
        """
        Create and initialize language-specific collections in the Weaviate database.

        Each collection includes vector and generative configurations.

        Raises:
            weaviate.exceptions.WeaviateConnectionError: If the database connection fails.
        """ 
        logger.info('Attempting collections creation for the database...')
        
        vector_config = Configure.Vectors.text2vec_transformers() 
        for collection_name in _collection_names:
            try:
                self._client.collections.create(
                    name=collection_name,
                    properties=[
                        Property(name='body', data_type=DataType.TEXT),
                        Property(name='chunk_id', data_type=DataType.TEXT),
                        Property(name='document_id', data_type=DataType.TEXT),
                        Property(name='programs', data_type=DataType.TEXT_ARRAY),
                        Property(name='source', data_type=DataType.TEXT),
                        Property(name='date', data_type=DataType.DATE)
                    ],
                    vector_config=vector_config)
                logger.info(f"Created collection {collection_name}")
            except Exception as e:
                logger.error(f"Failed to initialize collection '{collection_name}': {e}")
        logger.info('All collections were successfully instantiated in the database')


    @_with_connection
    def _delete_collections(self):
        """
        Delete all existing collections from the local Weaviate database.

        Raises:
            weaviate.exceptions.WeaviateConnectionError: If the connection to the database fails.
        """        
        logger.info("Initiating the deletion of stored collections.")
        for collection_name in _collection_names:
            if self._client.collections.exists(collection_name):
                self._client.collections.delete(collection_name)
                logger.info(f"Deleted collection {collection_name}")
            else:
                logger.warning(f"Cannot delete collection {collection_name}: collection does not exist!")
        
        logger.info("Finished the deletion of stored colections")
   

    @_with_connection
    def _create_backup(self) -> None:
        """
        Creates a backup instance from current weaviate database state and uploads it to selected backend storage service.
        """        
        backup_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
        logger.info("Initiating backup creation for the local weaviate database")
        try:
            result = self._client.backup.create(
                backup_id=f"hsg_wvtdb_backup_{backup_id}",
                backend=WEAVIATE_BACKUP_BACKEND,
                include_collections=_collection_names,
                wait_for_completion=True
            )
            logger.info(f"Creation of backup '{backup_id}' finished with response: {result}")
        except Exception as e:
            logger.error(f"Failed to create a backup due to an unexpected error: {e.message}")
            raise e


    @_with_connection
    def _restore_backup(self, backup_id: str):
        """
        Restores the state of the database from the provided backup.
        
        Args:
            backup_id(str): ID of the backup from which the database state should be restored.
        """        
        logger.info("Initiating restoration process from the backup '{backup_id}' for the local weaviate database")
        try:
            result = self._client.backup.restore(
                backup_id=backup_id,
                backend=WEAVIATE_BACKUP_BACKEND,
                include_collections=_collection_names,
                wait_for_completion=True,
            )
            logger.info(f"Restored backup '{backup_id}' with response: {result}")
        except Exception as e:
            logger.error(f"Failed to restore a backup due to an unexpected error: {e.message}")
            raise e


    @_with_connection
    def _checkhealth(self):
        """
        Check the connectivity and health status of the Weaviate database and its collections.

        Prints the connection status and verifies the existence of collections for each supported language.
        """
        connection_exists = self._client.is_connected()
        logger.info(f"Checking the connection to the local weaviate database: {'OK!' if connection_exists else 'ERROR'}")
        if not connection_exists: return 

        metainfo = self._client.get_meta()
        logger.info(f"Cluster metadata: hostname {metainfo['hostname']}, version {metainfo['version']}, modules {metainfo['modules'].keys()}")

        for collection_name in _collection_names:
            logger.info(f"Checking the existence of collection {collection_name}: "
                  f"{'OK!' if self._client.collections.exists(collection_name) else 'ERROR' }")


def parse_arguments():
    """
    Parse command-line arguments for managing Weaviate collections.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-dc', "--delete_collections", action='store_true', help='deletes all collections from the database')
    group.add_argument('-cc', "--create_collections", action='store_true', help='initializes the collections for different language contents separately')
    group.add_argument('-rc', "--redo_collections", action='store_true', help='deletes and creates the collections anew')

    group.add_argument('-ch', "--checkhealth", action='store_true', help='checks the connection to the database, existense of content collections...')
    group.add_argument('-cb', "--create_backup", action='store_true', help='creates a backup of the current state of the database')
    group.add_argument('-rb', "--restore_backup", type=str, help='restores the state of the database from the provided backup_id')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    service = WeaviateService()

    if args.create_backup:
       service._create_backup()

    if args.restore_backup:
        service._restore_backup(args.restore_backup)

    if any([args.delete_collections, args.redo_collections]):
        service._delete_collections()

    if any([args.create_collections, args.redo_collections]):
        service._create_collections()
    
    if any([args.checkhealth, args.create_collections, args.redo_collections]):
        service._checkhealth()
    
