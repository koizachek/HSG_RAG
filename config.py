"""
Configuration settings for the Executive Education RAG Chatbot.
"""
# ========================================= General Configuration ===========================================

# A list of ISO 639 language codes. Defines a list of languages in which 
# the application can operate. Defaults to ['en', 'de'].
AVAILABLE_LANGUAGES = ['en', 'de']

# =================================== Conversation State Configuration ======================================

# A boolean; either True or False. Enables the collection of user preferences 
# during conversation to avoid repetetive questions. Defaults to True. 
TRACK_USER_PROFILE = True 

# An integer. Defines the amount of user messages after which the language 
# of the conversation will be locked. If set to 0, the language will not be locked.
LOCK_LANGUAGE_AFTER_N_MESSAGES = 3

# An integer. Sets the maximum amount of conversation turns as the sum of user queries
# and agent responses. The conversation ends after the maximum turns amount is reached.
MAX_CONVERSATION_TURNS = 15

# ============================================ LLM Configuration ============================================

# A string, either 'openai', 'groq', 'open_router' or 'ollama' (local).
# Defines the main model provider for the application.
LLM_PROVIDER = 'openai' 

# A string. Defines the model that will be used by the application agents. 
OPENAI_MODEL = 'gpt-5.1'
# GROQ_MODEL = 
# OLLAMA_MODEL = 
# OPEN_ROUTER_MODEL = 

# ==================================== Weaviate Database Configuration ======================================

# A boolean; either True or False. 
# Defines whether the database is set as a local instance (via Docker container), 
# or as a cloud service. More information on https://docs.weaviate.io/weaviate.
WEAVIATE_IS_LOCAL = False

# A string. Defines the name of the colletions stored in the database.
# For each available language a new collection will be created
# with set name <WEAVIATE_COLLECTION_BASENAME>_<LANGUAGE>.
WEAVIATE_COLLECTION_BASENAME = 'hsg_rag_content'

# A string; either 'manual', 'filesystem' (local instance), 's3' (AWS).
# Defines the service for storing the database backups.
# More information on https://docs.weaviate.io/deploy/configuration/backups.
WEAVIATE_BACKUP_METHOD = 'manual'

# A string representing a path in the system where backups will be stored 
# only if WEAVIATE_BACKUP_METHOD is set to 'manual'.
BACKUPS_PATH = 'data/database/backups'

# A string representing a system path where collection properties will be stored.
PROPERTIES_PATH = 'data/database/properties'

# A string representing a system path where property strategies will be stored.
# More information on property strategies in the documentation.
STRATEGIES_PATH = 'data/database/strategies'

# An integer. Defines a connection timeout to the cloud weaviate service (in seconds). 
# Defaults to 90.
WEAVIATE_INIT_TIMEOUT = 90

# An integer. Defines the query response time limit upon querying the database (in seconds). 
# Defaults to 60.
WEAVIATE_QUERY_TIMEOUT = 60

# An integer. Defines the chunk insertion time limit when importing new chunks to database (in seconds).
# Defaults to 600
WEAVIATE_INSERT_TIMEOUT = 600

# ========================================== Cache Configuration ============================================

# A string; either 'local', 'cloud' (Redis) or 'dict'. Defaults to 'cloud'.
# Sets the default cache mode. More information on cache modes in documentation.
CACHE_MODE = 'cloud'

# An integer. Sets the reset time (time to live) in seconds for the cache storage.
# The cache storage will be cleared upon reset time exceedance.
# Defaults to 86400 seconds (24 hours).
CACHE_TTL = 86400 

# An integer. Maximum amount of cached messages that will be held in the cache storage.
# Defaults to 1000.
CACHE_MAX_SIZE = 1000 

# A string. Defines the IP adress to access the local cache storage. Defaults to 'localhost'.
CACHE_LOCAL_HOST = 'localhost'

# An integer. Defines the port for accessing the local cache storage. Defaults to 6379.
CACHE_LOCAL_PORT = 6379 

# ===================================== Data Processing Configuration =======================================

# EMBEDDING_MODEL = 

# A float in range from 0 to 1. Sets the threshold for english language in the language detector.
# If the language detection certanty is lower than the threshold, the English language will be returned.
LANG_AMBIGUITY_THRESHOLD = 0.6

# An integer. Defines the maximum amount of tokens pro single chunk.
MAX_TOKENS = 200

# An integer. Defines the amount of overlapping tokens between chunks to keep the context. 
CHUNK_OVERLAP = 100

# ======================================== Agent Chain Configuration ========================================

# A boolean; either True or False. Activates the response quality evaluation procedure
# for agentic responses. Defaults to True.
ENABLE_EVALUATE_RESPONSE_QUALITY = True

# A float in range from 0 to 1. Sets the treshold value for the quality evaluation.
# The fallback mechanism will be activated if the quality of the agentic response 
# is lower than the confidence threshold.
CONFIDENCE_THRESHOLD = 0.6

# An integer. Defines the amount of chunks that should be retrieved from the database 
# upon querying by subagents during conversation. Defaults to 4.
TOP_K_RETRIEVAL = 4  

# An integer. Sets the amount of model invocation retries after which the fallback model 
# will be invoked. Defaults to 3.
MODEL_MAX_RETRIES = 3

# An integer. Sets the maximum amount of words in the response from the lead agent.
MAX_RESPONSE_WORDS_LEAD = 100 

# An integer. Sets the maximum amount of words in the response for subagents.
MAX_RESPONSE_WORDS_SUBAGENT = 200

# A boolean; either True or False. If response chunking is enabled, long responses 
# from the lead agent will be split and retuned through multiple conversation turns.
ENABLE_RESPONSE_CHUNKING = True 

# ===========================================================================================================

# Base URLs for scraping
SCRAPE_URLS = [
    'https://apply.emba.unisg.ch/emba',
    'https://apply.emba.unisg.ch/iemba',
    'https://apply.emba.unisg.ch/embax',
    
    'https://emba.unisg.ch/programm/emba',
    'https://emba.unisg.ch/en/programm/emba',
    'https://emba.unisg.ch/programm/iemba',
    'https://emba.unisg.ch/en/programm/iemba',
    
    'https://emba.unisg.ch/en/embax',
    'https://embax.ch/programme/overview/',
    'https://embax.ch/programme/description/',
    'https://embax.ch/programme/timeline/',
]
