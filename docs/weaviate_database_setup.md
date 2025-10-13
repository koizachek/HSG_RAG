# Weaviate Database Setup

This project uses a local instance of a Weaviate vector database to store vector embeddings. The chosen embedding model is Sentence Transformers. The model is integrated in the embedding insertion pipeline and will be installed alongside the database.

## Installation steps
1. Create a new python virtual environment using `python -m venv venv`, activate the environment via `source venv/bin/activate`, install the needed requirements from the `requirements.txt` file if you haven't done it already.
2. Follow the installation guide to install [Docker Desktop](https://docs.docker.com/desktop/) on your device.
3. Navigate to `src/database` and locate the `docker-compose.yml` file. Inside this directory call the command `docker compose up -d` to install and setup the database and embedding model containers. Wait for installation to finish gracefully.
4. With the python environment activated, call the collection creation script from the `weaviate.py` located in the same directory using `python wvt_service.py --create_collections`. Inspect the logs to check whether the creation of the collections was successfull.

If you've managed to setup the database and create the collections, the installation process is finished and the database is accessible from the other parts of the program.

## Managing the database 
To manage the state of the database directly, multiple useful scripts were developed. The scripts can be called via the `weaviate.py` using the following arguments:

- `-cc` or `--create_collections`: initializes separate collections for different language contents.
- `-dc` or `--delete_collections`: deletes all collections and their contents from the database.
- `-rc` or `--redo_collections`: deletes the collections and creates them again.
- `-ch` or `--checkhealth`: checks the connection to the database and existence of the content collections.
- `-cb` or `--create_backup`: creates a backup of the current state of the database.
- `-rb` pr `--restore_backup`: restores the state of the database from the provided backup\_id.

## Data properties
Embeddings are stored in the corresponding language collection with a set of properties that define chunk metadata:

- body (TEXT): text content of the stored embedding.
- chunk\_id (TEXT): ID of the chunk defined by the data processor.
- document\_id (TEXT): ID of the document from which the chunk was derived (also defined by the data processor).
- programs (TEXT\_ARRAY): list of the EMBA programs that were identified in the document of the derived information.
- source (TEXT): source of the information (name of the document or the url).
- date (DATE): date when the data chunk was prepared for the insertion.


## WeaviateService
The WeaviateService class manages the connection and the interaction with the local database.
