from weaviate.collections.collection import Collection
import weaviate as wvt, weaviate.exceptions as wex, argparse, logging, os
from weaviate.classes.config import Configure, Property, DataType

logger = logging.getLogger(__name__)

AVAILABLE_LANGUAGES = ['en', 'de']
COLLECTION_BASENAME = 'hsg_rag_content'
get_collection_name = lambda lang: f'{COLLECTION_BASENAME}_{lang}'

class WeaviateService:
    """
    Service that initializes and manages the connection to the local Weaviate vector database.
    """
    def __init__(self):
        headers = {'X-OpenAI-Api-Key': os.getenv('OPENAI_API_KEY')}

        self._client: wvt.WeaviateClient = wvt.connect_to_local(headers=headers)
        logger.info('Connection with the local vector database instantiated')
        self._current_collection: Collection = None 
   

    def select_language(self, lang: str):
        if lang in AVAILABLE_LANGUAGES:
            collection_name = get_collection_name(lang)
            self._current_collection = self._client.collections.use(collection_name)
            logger.info(f"Selected collection {collection_name} as working collection")
        else:
            e = wex.WeaviateConnectionError("No collection for language '{lang}' was found in the database!")
            logger.error(e)
            raise e


    def batch_import(self, data_rows: list, lang: str = None) -> list:
        if lang: self.select_language(lang)
        if not self._current_collection:
            e = wex.WeaviateConnectionError("No working collection selected upon starting batch import!")
            logger.error(e)
            raise e

        import_errors = []
        logger.info(f"Initiating batch import for {lang(data_rows)} data rows")
        with self._current_collection.batch.fixed_size(batch_size=100, concurrent_requests=2) as batch:
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
        
        logger.info("Batch import finished")
        if import_errors:
            logger.info("Total import errors: {len(import_errors)}")
        
        return import_errors
    
    
    def query(self, query: str, limit: int = 10, lang: str = None): 
        if lang: self.select_language(lang)
        if not self._current_collection:
            e = wex.WeaviateConnectionError("No working collection selected upon querying!")
            logger.error(e)
            raise e


    def __del__(self):
        self._client.close()
        logger.info('Closed the connection with the local vector database')
    
    def is_connected(self):
        return self._client.is_ready()


def _delete_collections():
    service = WeaviateService()
    
    if not service.is_connected():
        raise wex.WeaviateConnectionError('Failed to establish a connection to the local Weaviate database!')
    
    for lang in AVAILABLE_LANGUAGES:
        collection_name = get_collection_name(lang)

        if service._client.collections.exists(collection_name):
            service._client.collections.delete(collection_name)


def _checkhealth():
    service = WeaviateService()
    connection_exists = service.is_connected()
    print(f"- Checking the connection to the local weaviate database: {'OK!' if connection_exists else 'ERROR'}")
    if not connection_exists: return 
    
    for lang in AVAILABLE_LANGUAGES:
        collection_name = get_collection_name(lang)
        print(f"- Checking the existence of collection {collection_name}: {
              'OK!' if service._client.collections.exists(collection_name) else 'ERROR' }", end='')

def _create_collections():
    """
    Initializes the collections for english and german contents separately.
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
    
    for lang in AVAILABLE_LANGUAGES:
        collection_name = get_collection_name(lang)
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
            logger.info(f"Created collection 'hsg_rag_content_en'")
        except Exception as e:
            logger.error(f"Failed to initialize collection '{collection_name}': {e}")
    logger.info('All collections were successfully instantiated in the database')


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-dc', "--delete_collections", action='store_true', help='deletes all collections from the database')
    parser.add_argument('-cc', "--create_collections", action='store_true', help='initializes the collections for english and german contents separately')
    parser.add_argument('-ch', "--checkhealth", action='store_true', help='checks the connection to the database, existense of content collections...')
    
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    
    if args.delete_collections:
        _delete_collections()

    if args.create_collections:
        _create_collections()
    
    if args.checkhealth:
        _checkhealth()
