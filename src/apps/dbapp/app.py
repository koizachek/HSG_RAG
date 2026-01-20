from tkinter import *
from src.database.weavservice import WeaviateService
from src.apps.dbapp.backup import init_backups_frame

class DatabaseApplication:
    def __init__(self) -> None:
        self._root = self._init_root()
        self._service = WeaviateService()
        
        self._backups_frame = init_backups_frame(self._root, self._service)
    
    def _init_root(self):
        root = Tk()
        root.title("Database Interface")
        root.geometry("600x500")

        return root

    def run(self):
        self._root.mainloop()
