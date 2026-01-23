import os
import threading
from tkinter import *
from tkinter import ttk
from tkinter import filedialog

from src.pipeline.pipeline import ImportPipeline
from src.apps.dbapp.framebase import CustomFrameBase
from src.database.weavservice import WeaviateService

class ImportFrame(CustomFrameBase):
    def __init__(self, parent, service: WeaviateService) -> None:
        super().__init__(parent, service)
        self._import_paths = dict()

    def init(self):
        main_frame = ttk.Frame(self._parent)
        main_frame.pack(fill=BOTH, expand=True)
        
        import_frame = ttk.Frame(main_frame)
        file_buttons_frame = ttk.Frame(main_frame)
        file_buttons_frame.pack(fill=X, side=TOP, anchor=NW, expand=True)

        files_treeview = ttk.Treeview(
            main_frame,
            columns=[],
            show='tree headings',
            selectmode='extended',
        )
        files_treeview.heading('#0', text='File name')
        files_treeview.column('#0', width=400)
        
        logging_textframe = Text(import_frame, width=40, height=16, state=DISABLED)

        def write_log(msg, filename: str = None):
            logging_textframe.config(state=NORMAL)
            logging_textframe.insert(END, msg)
            logging_textframe.config(state=DISABLED)

            if filename and 'DONE' in msg:
                #TODO: ADD TREEVIEW CHECKMARK HERE
                pass

        def update_treeview():
            for item in files_treeview.get_children(''):
                files_treeview.delete(item)

            for filename in self._import_paths.keys():
                files_treeview.insert('', 0, text=filename)

        def open_file_dialog():
            filepaths = filedialog.askopenfilenames(
                title='Select files to import',
                filetypes=(('PDF', '*.pdf'), ('Text files', '*.txt') ),
            )
            for path in filepaths:
                filename = os.path.basename(path)
                self._import_paths[filename] = path

            update_treeview()

        def remove_files():
            selection = files_treeview.selection()
            if not selection:
                return 

            for item in selection:
                filename = files_treeview.item(item)['text']
                del self._import_paths[filename]

            update_treeview()
        
        def import_task(): 
            filepaths = self._import_paths.values()
            ImportPipeline(logging_callback=write_log)\
                .import_many_documents(filepaths)

        def begin_import():
            disable_buttons()
            try:
                import_thread = threading.Thread(target=import_task)
                import_thread.start()
            except Exception as _:
                pass

        add_button = ttk.Button(file_buttons_frame, text='Add files', command=open_file_dialog)
        add_button.pack(side=LEFT, padx=15, pady=15)

        remove_button = ttk.Button(file_buttons_frame, text='Remove files', command=remove_files)
        remove_button.pack(side=LEFT, padx=15, pady=15)

        import_button = ttk.Button(import_frame, text='Begin Import', command=begin_import)
        import_button.pack(side=TOP, anchor=N, padx=15, pady=15)

        def disable_buttons():
            add_button.config(state=DISABLED)
            remove_button.config(state=DISABLED)
            import_button.config(state=DISABLED)
        
        ttk.Label(import_frame, text='Import status:').pack(side=TOP, anchor=NW, padx=15)
        
        files_treeview.pack(side=LEFT, anchor=W, fill=Y, expand=True, padx=15, pady=15)
        import_frame.pack(side=LEFT, anchor=W, fill=BOTH, expand=True)
        
        logging_textframe.pack(side=TOP, anchor=NW, fill=BOTH, expand=True, padx=15, pady=15)

        return main_frame
