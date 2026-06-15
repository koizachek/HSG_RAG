# Weaviate Database Setup

This project uses Weaviate Cloud to store retrieval chunks and vectors. The
application generates embeddings through OpenRouter
`openai/text-embedding-3-small` and stores them as self-provided vectors.

## Installation steps
1. Create a new python virtual environment using `python -m venv venv`, activate the environment via `source venv/bin/activate`, install the needed requirements from the `requirements.txt` file if you haven't done it already.
2. Configure `WEAVIATE_CLUSTER_URL`, `WEAVIATE_API_KEY`, and `OPEN_ROUTER_API_KEY`.
3. With the python environment activated, initialize the collections with `python main.py --weaviate init`. Inspect the logs to check whether collection creation was successful.

If you've managed to setup the database and create the collections, the installation process is finished and the database is accessible from the other parts of the program.

## Managing the database 
To manage the state of the database directly, multiple useful scripts were developed. The scripts can be called via the `weaviate.py` using the following arguments:

- `-cc` or `--create_collections`: initializes separate collections for different language contents.
- `-dc` or `--delete_collections`: deletes all collections and their contents from the database.
- `-rc` or `--redo_collections`: deletes the collections and creates them again.
- `-ch` or `--checkhealth`: checks the connection to the database and existence of the content collections.
- `-cb` or `--create_backup`: creates a backup of the current state of the database.
- `-rb` pr `--restore_backup`: restores the state of the database from the provided backup\_id.

When changing embedding model, tokenizer, or vector dimensions, rebuild the collections and re-import content:

```bash
python main.py --weaviate redo
python main.py --scrape
```

Run `python main.py --imports ...` afterward for any local documents that are
part of the knowledge base.

## Data properties
Embeddings are stored in the corresponding language collection with a set of properties that define chunk metadata:

- body (TEXT): text content of the stored embedding.
- chunk\_id (TEXT): ID of the chunk defined by the data processor.
- document\_id (TEXT): ID of the document from which the chunk was derived (also defined by the data processor).
- programs (TEXT\_ARRAY): list of the EMBA programs that were identified in the document of the derived information.
- source (TEXT): source of the information (name of the document or the url).
- date (DATE): date when the data chunk was prepared for the insertion.


## WeaviateService
The WeaviateService class manages the connection and interaction with Weaviate Cloud.
