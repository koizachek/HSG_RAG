from tkinter import *
from tkinter import ttk
from src.database.weavservice import WeaviateService
from src.apps.dbapp.backup import init_backups_frame
from src.apps.dbapp.config import SchemaConfigurationFrame

from src.utils.logging import get_logger

logger = get_logger("db_inter")

class DatabaseApplication:
    def __init__(self) -> None:
        self._root = Tk()
        self._service = WeaviateService()
        
        self._root.title("Database Interface")
        self._root.geometry("810x500")
        
        notebook = ttk.Notebook(self._root)
        notebook.pack(fill=BOTH, expand=True)

        backups_frame = init_backups_frame(notebook, self._service)
        config_frame = SchemaConfigurationFrame(notebook, self._service).init() 
        
        notebook.add(backups_frame, text='Backups')
        notebook.add(config_frame, text='Schemas')

        logger.info("Application initialization finished")

    def run(self):
        self._root.mainloop()
