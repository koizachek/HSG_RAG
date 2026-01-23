from tkinter import *
from tkinter import ttk
from src.apps.dbapp.framebase import CustomFrameBase
from src.database.weavservice import WeaviateService

class MainFrame(CustomFrameBase):
    def __init__(self, parent, service: WeaviateService) -> None:
        super().__init__(parent, service)
