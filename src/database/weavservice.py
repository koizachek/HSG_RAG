from functools import reduce
import weaviate as wvt
import datetime, os
from threading import Lock

from time import perf_counter, sleep
from weaviate.classes.config import Configure, Property, DataType
from weaviate.collections.classes.grpc import MetadataQuery
from weaviate.collections.collection import Collection
from weaviate.classes.init import AdditionalConfig, Timeout
from weaviate.classes.query import Filter
from weaviate.config import AdditionalConfig

from src.utils.logging import get_logger
from config import WeaviateConfiguration as wvtconf, AVAILABLE_LANGUAGES, HASH_FILE_PATH

logger = get_logger("weaviate_service")

_get_collection_name = lambda lang: f'{wvtconf.WEAVIATE_COLLECTION_BASENAME}_{lang}'
_collection_names = [_get_collection_name(lang) for lang in AVAILABLE_LANGUAGES]


class WeaviateService:
    """
    Provides an interface for interacting with the Weaviate vector database.
    Handles initialization, data import, and hybrid queries.
    """
    
    _instance = None 
    _init_lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize the Weaviate service.
        """
        if hasattr(self, '_initialized'):
            return 

        self._connection_type = 'local' if wvtconf.is_local() else 'cloud'
        self._client = None 
        self._client_lock = Lock()
        
        # Some parameters to ensure that the connection will not be closed 
        # during long pauses in conversations
        self._last_query_time = perf_counter()
        self._idle_timeout = 25 * 60
        self._initialized = True

        # Initialize the client for the first time 
        logger.info("Initializing Weaviate service...")
        try:
            self._init_client()
            logger.info("Weaviate service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Weaviate service: {e}")
            raise e


    def _init_client(self) -> wvt.WeaviateClient:
        """
        Initializes the weaviate client with additional configuration.
        Performs a warm-up querying to speed-up the subsequent calls.

        Returns:
            configured Weaviate client instance on successfull connection.
        
        Raises:
            WeaviateConnectionError of the last failed connection if connection fails after 3 retires.
        """
        # Returns the client if it hasn't been idling for too long 
        if self._client is not None:
            time_since_query = perf_counter() - self._last_query_time
            if time_since_query < self._idle_timeout:
                return self._client
            
            # The connection might be closed, clients has to be reconnected 
            logger.warning(f"Client has been idling for too long. Reconnecting to prevent server-side closure...")
            try:
                self._client.close()
            except Exception as _:
                pass 

            self._client = None 
        
        # Client initialization 
        with self._client_lock:
            if self._client:
                return self._client

            retries = 0
            last_exception: Exception = None
            while retries < 3:
                try:
                    if wvtconf.is_local():
                        self._client = wvt.connect_to_local()
                        break
                    
                    cluster_url = wvtconf.CLUSTER_URL
                    if not cluster_url.startswith('http'):
                        cluster_url = f"https://{cluster_url}"

                    self._client = wvt.connect_to_weaviate_cloud(
                        cluster_url=cluster_url,
                        auth_credentials=wvtconf.WEAVIATE_API_KEY,
                        additional_config=AdditionalConfig(
                            timeout=Timeout(
                                init=wvtconf.INIT_TIMEOUT, 
                                query=wvtconf.QUERY_TIMEOUT, 
                                insert=wvtconf.INSERT_TIMEOUT,
                            ),
                            skip_init_checks=False,
                        ),
                        headers={
                            "X-HuggingFace-Api-Key": wvtconf.HUGGING_FACE_API_KEY,
                        },
                    ) 

                    # Warm-up query 
                    logger.info("Running warm-up query to initialize server...")
                    try:
                        collection = _get_collection_name(AVAILABLE_LANGUAGES[0])
                        self._client.collections.exists(collection)
                        logger.info("Warm-up finished - server is ready!")
                    except Exception as warmup_err:
                        logger.warning(f"Warm-up query failed (non-critical): {warmup_err}")
                    
                    break
                except Exception as e:
                    last_exception = e
                    logger.error(f"Failed to establish connection: {e}")
                    retries += 1 
                    sleep(1)
            
            if retries == 3:
                logger.error(f"Failed after 3 retries!")
                raise last_exception

            logger.info(f"Successully connected to the {self._connection_type} weaviate database")
            self._last_query_time = perf_counter()
            return self._client


    def _select_collection(self, lang: str) -> tuple[Collection, str]:
        """
        Select a language-specific collection as the active working collection.

        Args:
            lang (str): Acceptable language code.

        Raises:
            weaviate.exceptions.WeaviateConnectionError: If the specified language collection does not exist.
        """
        if lang not in AVAILABLE_LANGUAGES:
            logger.error(f"No collection for language '{lang}' was found in the database")
            return None, ''

        collection_name = _get_collection_name(lang)
        logger.info(f"Using collection {collection_name}")

        client = self._init_client()
        return client.collections.use(collection_name), collection_name


    def batch_import(self, data_rows: list, lang: str) -> list:
        """
        Perform a batch import of multiple objects into the current collection.

        Args:
            data_rows (list): List of dictionaries representing the data rows to import.
            lang (str, optional): Language collection to use. If not provided, uses the current one.

        Returns:
            list[dict]: List of failed imports with error details, if any.

        Raises:
            If no active collection is available or a connection error was catched.
        """        
        collection, collection_name = self._select_collection(lang)
        if collection is None:
            logger.error("No working collection selected!")
            return []

        import_errors = []
        logger.info(f"Batch importing {len(data_rows)} rows into {collection_name}")
        
        try:
            with self._client_lock:
                with collection.batch.fixed_size(batch_size=100, concurrent_requests=2) as batch:
                    for idx, data_row in enumerate(data_rows):
                        try:
                            batch.add_object(properties=data_row)
                        except Exception as e:
                            import_errors.append({'index': idx, 'chunk_id': data_row['chunk_id'], 'error': str(e)})
                            
                        if idx % 20 == 0 and idx > 0:
                            if batch.number_errors > 0:
                                logger.info(f"Failed imports at index {idx}: {batch.number_errors}")
            
            self._last_query_time = perf_counter()
            logger.info(f"Batch import finished. Total errors: {len(import_errors)}")
            
        except Exception as e:
            if 'connection' in str(e).lower():
                logger.error(f"Connection error during batch import: {e}")
                self._client = None
            raise e  

        return import_errors
    
    @staticmethod
    def _create_property_filter(prop, values) -> Filter:
        match prop:
            case 'programs':
                return Filter.by_property('programs').contains_any(values)
            case _:
                return None


    def query(self, query: str, lang: str, property_filters: dict[str], limit: int = 5) -> dict:
        """
        Execute a hybrid semantic and keyword query against the active collection with automatic reconnection on idle timeout.

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
        retry_count = 0 
        max_retries = 2
            
        filters = [self._create_property_filter(prop, values) 
                   for prop, values in property_filters.items()] if property_filters else None
        filters = reduce(lambda f1, f2: f1 & f2, filters)

        while retry_count < max_retries:
            try:
                collection, collection_name = self._select_collection(lang)
                if collection is None:
                    logger.error("No working collection selected upon starting of the querying!")
                    return [], 0
                
                logger.info(f"Querying collection {collection_name}")
                query_start_time = perf_counter()

                with self._client_lock:
                    resp = collection.query.hybrid(
                        query=query,
                        filters=filters,
                        limit=limit,
                        return_metadata=MetadataQuery.full()
                    )
                elapsed = perf_counter() - query_start_time
                self._last_query_time = perf_counter()
                logger.info(f"Querying retrieved {len(resp.objects)} objects in {elapsed:3.2f} seconds")

                return (resp, elapsed)
            except Exception as e:
                if any(err_type in str(e).lower() for err_type in ['reset', 'closed', 'grpc', 'unavailable']):
                    retry_count += 1 
                    logger.warning(f"Connection error detected: {e}. Retrying...")

                    if retry_count == max_retries:
                        raise e
                else: # Probably not a server issue
                    raise e


    def _create_collections(self):
        """
        Create and initialize language-specific collections.
        
        Creates collections for all available languages with vector configuration.
        """
        try:
            client = self._init_client()
            logger.info('Attempting collections creation...')
            
            vector_config = (
                Configure.Vectors.text2vec_transformers() if wvtconf.is_local() 
                else Configure.Vectors.text2vec_huggingface(
                    name='hsg_rag_embeddings',
                    source_properties=['body'],
                    model="sentence-transformers/all-MiniLM-L6-v2",
                )
            )
            
            successful_creations = 0
            
            with self._client_lock:
                for collection_name in _collection_names:
                    try:
                        client.collections.create(
                            name=collection_name,
                            properties=[
                                Property(name='body', data_type=DataType.TEXT),
                                Property(name='chunk_id', data_type=DataType.TEXT),
                                Property(name='document_id', data_type=DataType.TEXT),
                                Property(name='programs', data_type=DataType.TEXT_ARRAY),
                                Property(name='source', data_type=DataType.TEXT),
                                Property(name='date', data_type=DataType.DATE)
                            ],
                            vector_config=vector_config
                        )
                        logger.info(f"Created collection {collection_name}")
                        successful_creations += 1
                    except Exception as e:
                        logger.error(f"Failed to create collection '{collection_name}': {e}")
            
            self._last_query_time = perf_counter()
            
            if successful_creations == len(_collection_names):
                logger.info('All collections successfully instantiated')
            else:
                logger.warning(f"Only {successful_creations}/{len(_collection_names)} collections created")
                
        except Exception as e:
            logger.error(f"Collections creation failed: {e}")
            self._client = None
            raise e


    def _delete_collections(self):
        """
        Delete all existing collections from the database.
        
        Also removes the hash file if it exists.        
        """
        try:
            client = self._init_client()
            logger.info("Initiating deletion of stored collections...")
            
            deleted_count = 0
            with self._client_lock:
                for collection_name in _collection_names:
                    try:
                        if client.collections.exists(collection_name):
                            client.collections.delete(collection_name)
                            logger.info(f"Deleted collection {collection_name}")
                            deleted_count += 1
                        else:
                            logger.warning(f"Collection {collection_name} does not exist")
                    except Exception as e:
                        logger.error(f"Failed to delete collection {collection_name}: {e}")
            
            self._last_query_time = perf_counter()
            logger.info(f"Deleted {deleted_count}/{len(_collection_names)} collections")
            
            # Clean up hash file
            if os.path.exists(HASH_FILE_PATH):
                try:
                    logger.info(f"Removing hash file: {HASH_FILE_PATH}")
                    os.remove(HASH_FILE_PATH)
                    logger.info("Hash file deleted successfully")
                except Exception as e:
                    logger.error(f"Failed to delete hash file: {e}")
                    
        except Exception as e:
            logger.error(f"Collections deletion failed: {e}")
            self._client = None
            raise e


    def _create_backup(self) -> None:
        """
        Create a backup of the current database state.
        
        Uploads backup to configured backend storage.         
        """
        try:
            client = self._init_client()
            backup_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
            logger.info(f"Initiating backup creation for {self._connection_type} database")
            
            with self._client_lock:
                result = client.backup.create(
                    backup_id=f"hsg_wvtdb_backup_{backup_id}",
                    backend=wvtconf.WEAVIATE_BACKUP_BACKEND,
                    include_collections=_collection_names,
                    wait_for_completion=True
                )
            
            self._last_query_time = perf_counter()
            logger.info(f"Backup '{backup_id}' created successfully: {result}")
            
        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            raise e


    def _restore_backup(self, backup_id: str):
        """
        Restore the database state from a backup.
        
        Restores specified collections from backup.
        
        Args:
            backup_id: ID of the backup to restore from
            
        Raises:
            Exception if backup restoration fails
        """
        try:
            client = self._init_client()
            logger.info(f"Initiating restoration from backup '{backup_id}' for {self._connection_type} database")
            
            with self._client_lock:
                result = client.backup.restore(
                    backup_id=backup_id,
                    backend=wvtconf.WEAVIATE_BACKUP_BACKEND,
                    include_collections=_collection_names,
                    wait_for_completion=True,
                )
            
            self._last_query_time = perf_counter()
            logger.info(f"Backup '{backup_id}' restored successfully: {result}")
            
        except Exception as e:
            error_msg = str(e).lower()
            if 'connection' in error_msg:
                logger.error(f"Connection error during backup restore: {e}. Will reconnect on next operation.")
                self._client = None
            logger.error(f"Backup restoration failed: {e}")
            raise e


    def _checkhealth(self) -> bool:
        """
        Check the connectivity and health status of the Weaviate database.
        
        Verifies:
        - Connection to the database
        - Database metadata and version
        - Existence of all expected collections
        - Module availability
        
        Returns:
            True if all health checks pass, False otherwise
        """
        try:
            client = self._init_client()
            
            # Check basic connectivity
            is_connected = False
            with self._client_lock:
                is_connected = client.is_connected()
            
            connection_status = "✓ OK" if is_connected else "✗ ERROR"
            logger.info(f"Connection to {self._connection_type} database: {connection_status}")
            
            if not is_connected:
                logger.error("Database connection check failed")
                return False
            
            # Get and log metadata
            try:
                with self._client_lock:
                    metainfo = client.get_meta()
                
                # Format module information
                modules = metainfo.get('modules', {})
                modules_list = list(modules.keys()) if isinstance(modules, dict) else modules
                modules_str = ', '.join(str(m) for m in modules_list) if modules_list else 'None'
                
                # Truncate long module strings for logging
                if len(modules_str) > 50:
                    modules_str = modules_str[:47] + '...'
                
                # Log connection details
                if wvtconf.is_local():
                    logger.info(
                        f"Database metadata: "
                        f"HOSTNAME={metainfo.get('hostname', 'unknown')}, "
                        f"VERSION={metainfo.get('version', 'unknown')}, "
                        f"MODULES={modules_str}"
                    )
                else:
                    logger.info(
                        f"Database metadata: "
                        f"VERSION={metainfo.get('version', 'unknown')}, "
                        f"MODULES={modules_str}"
                    )
                
            except Exception as e:
                logger.warning(f"Could not retrieve database metadata: {e}")
            
            # Check collection existence
            all_collections_exist = True
            
            with self._client_lock:
                for collection_name in _collection_names:
                    try:
                        exists = client.collections.exists(collection_name)
                        status = "✓ OK" if exists else "✗ MISSING"
                        logger.info(f"Collection '{collection_name}': {status}")
                        
                        if not exists:
                            all_collections_exist = False
                            
                    except Exception as e:
                        logger.error(f"Error checking collection '{collection_name}': {e}")
                        all_collections_exist = False
            
            # Update last health check time
            self._last_query_time = perf_counter()
            
            # Log overall health status
            if is_connected and all_collections_exist:
                logger.info("✓ Database health check PASSED - All systems operational")
                return True
            else:
                logger.warning("✗ Database health check FAILED - Some issues detected")
                return False
                
        except Exception as e:
            error_msg = str(e).lower()
            if 'connection' in error_msg:
                logger.error(f"Connection error during health check: {e}. Will reconnect on next operation.")
                self._client = None
            logger.error(f"Health check failed: {e}")
            return False


def parse_arguments():
    """
    Parse command-line arguments for managing Weaviate collections.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Weaviate database management utility'
    )
    group = parser.add_mutually_exclusive_group()
    
    group.add_argument(
        '-dc', "--delete_collections", 
        action='store_true', 
        help='Delete all collections from the database'
    )
    group.add_argument(
        '-cc', "--create_collections", 
        action='store_true', 
        help='Initialize collections for different language contents'
    )
    group.add_argument(
        '-rc', "--redo_collections", 
        action='store_true', 
        help='Delete and recreate all collections'
    )
    group.add_argument(
        '-ch', "--checkhealth", 
        action='store_true', 
        help='Check database connection and collection existence'
    )
    group.add_argument(
        '-cb', "--create_backup", 
        action='store_true', 
        help='Create a backup of the current database state'
    )
    group.add_argument(
        '-rb', "--restore_backup", 
        type=str, 
        metavar='BACKUP_ID',
        help='Restore database from a backup (provide backup_id)'
    )
    
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
    
