import weaviate as wvt, weaviate.exceptions as wex, argparse, logging
from weaviate.classes.config import Configure

logger = logging.getLogger(__name__)

class WeaviateService:
    """
    Service that initializes and manages the connection to the local Weaviate vector database.
    """
    def __init__(self):
        self._client: wvt.WeaviateClient = wvt.connect_to_local()
        logger.info('Connection with the local vector database instantiated')

    def __del__(self):
        self._client.close()
        logger.info('Closed the connection with the local vector database')
    
    def is_connected(self):
        return self._client.is_ready()


def _checkhealth():
    service = WeaviateService()
    connection_exists = service.is_connected()
    print(f"- Checking the connection to the local weaviate database: {'OK!' if connection_exists else 'ERROR'}")
    if not connection_exists: return 
    
    for lang in ['en', 'de']:
        print(f"- Checking the existence of collection 'hsg_rag_content_{lang}': ", end='')
        try:
            service._client.collections.use(f'hsg_rag_content_{lang}')
            print('OK!')
        except Exception as _:
            print('ERROR')


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
    
    for lang in ['en', 'de']:
        collection_name = f'hsg_rag_content_{lang}'
        try:
            service._client.collections.create(
                name=collection_name,
                vector_config=vector_config,            
                generative_config=generative_config)
            logger.info(f"Created collection 'hsg_rag_content_en'")
        except Exception as e:
            logger.error(f"Failed to initialize collection '{collection_name}': {e}")
    logger.info('All collections were successfully instantiated in the database')


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-cc', "--create_collections", action='store_true', help='initializes the collections for english and german contents separately')
    parser.add_argument('-ch', "--checkhealth", action='store_true', help='checks the connection to the database, existense of content collections...')
    
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    if args.create_collections:
        _create_collections()
    
    if args.checkhealth:
        _checkhealth()
