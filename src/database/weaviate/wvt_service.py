import weaviate as wvt, weaviate.exceptions as wex 
import argparse, logging, os, datetime

from time import perf_counter
from dataclasses import dataclass
from weaviate.collections.classes.grpc import MetadataQuery
from weaviate.collections.collection import Collection
from weaviate.classes.config import Configure, Property, DataType

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

AVAILABLE_LANGUAGES = ['en', 'de']

DB_BACKUP_BACKEND = ""
COLLECTION_BASENAME = 'hsg_rag_content'
_get_collection_name = lambda lang: f'{COLLECTION_BASENAME}_{lang}'
_collection_names = [_get_collection_name(lang) for lang in AVAILABLE_LANGUAGES]


@dataclass
class _Collection:
    it: Collection
    name: str


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
        headers = {'X-OpenAI-Api-Key': os.getenv('OPENAI_API_KEY') or "no-key"}

        self._client: wvt.WeaviateClient = wvt.connect_to_local(headers=headers)
        logger.info('Connection with the local vector database instantiated')

        self._collections: dict[str, _Collection] = {}
        self._current_collection: _Collection = None 
   

    def select_language(self, lang: str) -> None:
        """
        Select a language-specific collection as the active working collection.

        Args:
            lang (str): Acceptable language code.

        Raises:
            weaviate.exceptions.WeaviateConnectionError: If the specified language collection does not exist.
        """
        if lang in AVAILABLE_LANGUAGES:
            if lang not in self._collections:
                collection_name = _get_collection_name(lang)
                self._collections[lang] = _Collection(it=self._client.collections.use(collection_name), name=collection_name)
            
            self._current_collection = self._collections[lang]
            logger.info(f"Selected collection {collection_name} as working collection")
        else:
            e = wex.WeaviateConnectionError("No collection for language '{lang}' was found in the database!")
            logger.error(e)
            raise e


    def batch_import(self, data_rows: list, lang: str = None) -> list:
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
        if lang: self.select_language(lang)
        if not self._current_collection:
            e = wex.WeaviateConnectionError("No working collection selected upon starting batch import!")
            logger.error(e)
            raise e

        import_errors = []
        logger.info(f"Initiating batch import for {len(data_rows)} data rows into collection {self._current_collection.name}")
        with self._current_collection.it.batch.fixed_size(batch_size=100, concurrent_requests=2) as batch:
            for idx, data_row in enumerate(data_rows):
                try:
                    batch.add_object(properties=data_row)
                except Exception as e:
                    import_errors.append({'index': idx, 'data': data_row, 'error': str(e)})
                    continue
                
                # Periodical checks for failed imports
                if idx % 20 == 0 and idx > 0:
                    if batch.number_errors > 0:
                        logger.info(f"Amount of failed imports at index {idx}: {batch.number_errors}")
                        last_failed_object = self._current_collection.batch.failed_objects[-1]
                        logger.info(f"Last failure: {last_failed_object.message}")
        
        logger.info(f"Batch import finished for {self._current_collection.name}")
        if import_errors:
            logger.info("Total import errors: {len(import_errors)}")
        
        return import_errors
    
    
    def query(self, query: str, query_properties: list[str] = None, limit: int = 5, distance: float = 0.25, lang: str = None) -> dict:
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
        if lang: self.select_language(lang)
        if not self._current_collection:
            e = wex.WeaviateConnectionError("No working collection selected upon querying!")
            logger.error(e)
            raise e
        
        logger.info(f"Querying collection {self._current_collection.name}")
        query_start_time = perf_counter()
        resp = self._current_collection.it.query.hybrid(
            query=query,
            query_properties=query_properties,
            distance=distance,
            limit=limit,
            return_metadata=MetadataQuery.full()
        )
        elapsed = perf_counter() - query_start_time
        logger.info(f"Querying retrieved {len(resp.objects)} objects in {elapsed} seconds")

        return (resp, elapsed)


    def __del__(self):
        """
        Destructor method to safely close the Weaviate client connection.
        """
        self._client.close()
        logger.info('Closed the connection with the local vector database')


    def is_connected(self):
        """
        Check if the client is successfully connected to the Weaviate instance.

        Returns:
            bool: True if the client is connected, False otherwise.
        """
        return self._client.is_ready()


def _create_backup() -> None:
    """
    Creates a backup instance from current weaviate database state and uploads it to selected backend storage service.
    """
    service = WeaviateService()
    
    if not service.is_connected():
        raise wex.WeaviateConnectionError('Failed to establish a connection to the local Weaviate database!')
    
    backup_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
    logger.info("Initiating backup creation for the local weaviate database")
    try:
        result = service._client.backup.create(
            backup_id=f"hsg_wvtdb_backup_{backup_id}",
            backend=DB_BACKUP_BACKEND,
            include_collections=_collection_names,
            wait_for_completion=True
        )
        logger.info(f"Creation of backup '{backup_id}' finished with response: {result}")
    except Exception as e:
        logger.error(f"Failed to create a backup due to an unexpected error: {e.message}")
        raise e


def _restore_backup(backup_id: str):
    """
    Restores the state of the database from the provided backup.
    
    Args:
        backup_id(str): ID of the backup from which the database state should be restored.
    """
    service = WeaviateService()
    
    if not service.is_connected():
        raise wex.WeaviateConnectionError('Failed to establish a connection to the local Weaviate database!')
    
    logger.info("Initiating restoration process from the backup '{backup_id}' for the local weaviate database")
    try:
        result = service._client.backup.restore(
            backup_id=backup_id,
            backend=DB_BACKUP_BACKEND,
            include_collections=_collection_names,
            wait_for_completion=True,
        )
        logger.info(f"Restored backup '{backup_id}' with response: {result}")
    except Exception as e:
        logger.error(f"Failed to restore a backup due to an unexpected error: {e.message}")
        raise e


def _delete_collections():
    """
    Delete all existing collections from the local Weaviate database.

    Raises:
        weaviate.exceptions.WeaviateConnectionError: If the connection to the database fails.
    """
    service = WeaviateService()
    
    if not service.is_connected():
        raise wex.WeaviateConnectionError('Failed to establish a connection to the local Weaviate database!')
    
    logger.info("Initiating the deletion of stored collections.")
    for collection_name in _collection_names:
        if service._client.collections.exists(collection_name):
            service._client.collections.delete(collection_name)
            logger.info(f"Deleted collection {collection_name}")
        else:
            logger.warning(f"Cannot delete collection {collection_name}: collection does not exist!")
    
    logger.info("Finished the deletion of stored colections")


def _checkhealth():
    """
    Check the connectivity and health status of the Weaviate database and its collections.

    Prints the connection status and verifies the existence of collections for each supported language.
    """
    service = WeaviateService()
    connection_exists = service.is_connected()
    logger.info(f"Checking the connection to the local weaviate database: {'OK!' if connection_exists else 'ERROR'}")
    if not connection_exists: return 
    
    for collection_name in _collection_names:
        logger.info(f"Checking the existence of collection {collection_name}: "
              f"{'OK!' if service._client.collections.exists(collection_name) else 'ERROR' }")


def _create_collections():
    """
    Create and initialize language-specific collections in the Weaviate database.

    Each collection includes vector and generative configurations.

    Raises:
        weaviate.exceptions.WeaviateConnectionError: If the database connection fails.
    """
    logger.info('Connecting to the local weaviate database...')
    service = WeaviateService()
    
    if not service.is_connected():
        raise wex.WeaviateConnectionError('Failed to establish a connection to the local Weaviate database!')

    logger.info('Connection with the weaviate database established successfully')
    logger.info('Attempting collections creation for the database...')
    
    vector_config = Configure.Vectors.text2vec_ollama(
        api_endpoint="http://ollama:11434", model="nomic-embed-text")
    generative_config = Configure.Generative.ollama(
        api_endpoint="http://ollama:11434", model="llama3.2")
    
    for collection_name in _collection_names:
        try:
            service._client.collections.create(
                name=collection_name,
                properties=[
                    Property(name='body', data_type=DataType.TEXT),
                    Property(name='chunk_id', data_type=DataType.TEXT),
                    Property(name='document_id', data_type=DataType.TEXT),
                    Property(name='programs', data_type=DataType.TEXT_ARRAY),
                    Property(name='source', data_type=DataType.TEXT),
                    Property(name='date', data_type=DataType.DATE)
                ],
                vector_config=vector_config,            
                generative_config=generative_config)
            logger.info(f"Created collection {collection_name}")
        except Exception as e:
            logger.error(f"Failed to initialize collection '{collection_name}': {e}")
    logger.info('All collections were successfully instantiated in the database')


def parse_arguments():
    """
    Parse command-line arguments for managing Weaviate collections.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-dc', "--delete_collections", action='store_true', help='deletes all collections from the database')
    group.add_argument('-cc', "--create_collections", action='store_true', help='initializes the collections for english and german contents separately')
    group.add_argument('-ch', "--checkhealth", action='store_true', help='checks the connection to the database, existense of content collections...')
    group.add_argument('-cb', "--create_backup", action='store_true', help='creates a backup of the current state of the database')
    group.add_argument('-rb', "--restore_backup", type=str, help='restores the state of the database from the provided backup_id')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    
    if args.create_backup:
        _create_backup()

    if args.restore_backup:
        _restore_backup(args.restore_backup)

    if args.delete_collections:
        _delete_collections()

    if args.create_collections:
        _create_collections()
    
    if args.checkhealth:
        _checkhealth()
    
