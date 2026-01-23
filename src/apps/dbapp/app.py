from tkinter import *
from tkinter import ttk
from src.database.weavservice import WeaviateService

from src.apps.dbapp.mainframe import MainFrame
from src.apps.dbapp.query import QueryFrame
from src.apps.dbapp.imports import ImportFrame
from src.apps.dbapp.backup import BackupsFrame
from src.apps.dbapp.collections import CollectionsFrame
from src.apps.dbapp.config import SchemaConfigurationFrame

from src.utils.logging import get_logger

logger = get_logger("db_inter    ")

class DatabaseApplication:
    def __init__(self) -> None:
        self._root = Tk()
        self._service = WeaviateService()
        
        self._root.title("Database Interface")
        self._root.geometry("810x500")
        
        notebook = ttk.Notebook(self._root)
        notebook.pack(fill=BOTH, expand=True)

        main_frame = MainFrame(notebook, self._service).init()
        import_frame = ImportFrame(notebook, self._service).init() 
        config_frame = SchemaConfigurationFrame(notebook, self._service).init() 
        collections_frame = CollectionsFrame(notebook, self._service).init()
        query_frame = QueryFrame(notebook, self._service).init()
        backups_frame = BackupsFrame(notebook, self._service).init()
        
        notebook.add(main_frame, text='Main')
        notebook.add(import_frame, text='Import')
        notebook.add(config_frame, text='Schemas')
        notebook.add(collections_frame, text='Collections')
        notebook.add(query_frame, text='Query')
        notebook.add(backups_frame, text='Backups')

        logger.info("Application initialization finished")

    def run(self):
        self._root.mainloop()
