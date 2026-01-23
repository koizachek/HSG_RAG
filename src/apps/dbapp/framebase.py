from tkinter import *
from tkinter import ttk 
from src.database.weavservice import WeaviateService

class CustomFrameBase:
    def __init__(self, parent, service: WeaviateService) -> None:
        self._parent  = parent
        self._service = service


    def init(self) -> ttk.Frame:
        main_frame = ttk.Frame(self._parent)
        main_frame.pack()

        return main_frame
