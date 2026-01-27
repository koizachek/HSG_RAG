import os
import threading
from tkinter import *
from tkinter import ttk
from tkinter import filedialog

from src.pipeline.pipeline import ImportPipeline
from src.apps.dbapp.framebase import CustomFrameBase
from src.database.weavservice import WeaviateService
from src.pipeline.utilclasses import ProcessingResult
from src.utils.lang import get_language_name

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
        
        import_buttons_frame = ttk.Frame(import_frame)
        import_buttons_frame.pack(side=TOP, anchor=W, expand=True)

        files_treeview = ttk.Treeview(
            main_frame,
            columns=[],
            show='tree headings',
            selectmode='extended',
        )
        files_treeview.heading('#0', text='File name')
        files_treeview.column('#0', width=400)
        
        logging_textframe = Text(import_frame, width=40, height=16, state=DISABLED)

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
        
        def change_button_state(state):
            add_button.config(state=state)
            remove_button.config(state=state)
            import_button.config(state=state)

        add_button = ttk.Button(file_buttons_frame, text='Add files', command=open_file_dialog)
        add_button.pack(side=LEFT, padx=15, pady=15)

        remove_button = ttk.Button(file_buttons_frame, text='Remove files', command=remove_files)
        remove_button.pack(side=LEFT, padx=15, pady=15)

        import_button = ttk.Button(import_buttons_frame, text='Begin Import', 
            command=lambda: self._import_callback(change_button_state, clean_coll_var.get())
        )
        import_button.pack(side=LEFT, padx=15, pady=15)
        
        clean_coll_var = BooleanVar(value=False)
        clean_coll_checkbutton = ttk.Checkbutton(
                import_buttons_frame, 
                text='Clean Collections', 
                variable=clean_coll_var,
        )
        clean_coll_checkbutton.pack(side=RIGHT, padx=15, pady=15)
 
        ttk.Label(import_frame, text='Import status:').pack(side=TOP, anchor=NW, padx=15)
        
        files_treeview.pack(side=LEFT, anchor=W, fill=Y, expand=True, padx=15, pady=15)
        import_frame.pack(side=LEFT, anchor=W, fill=BOTH, expand=True)
        
        logging_textframe.pack(side=TOP, anchor=NW, fill=BOTH, expand=True, padx=15, pady=15)

        return main_frame


    def _import_callback(self, button_state_callback, clean_coll: bool):
        dialog = Toplevel()
        dialog.title("Import status")
        dialog.geometry("600x400")

        current_import_label = ttk.Label(dialog, text='Initiating the import pipeline...')
        current_import_label.pack(side=TOP, padx=15, pady=15)
        
        progress_bar = ttk.Progressbar(dialog, length=200, value=0, maximum=100)
        progress_bar.pack(side=TOP, padx=15, pady=15)

        chunks_treeview = ttk.Treeview(
            dialog,
            columns=['chunks', 'lang'],
            show='tree headings',
            selectmode='extended',
        )
        chunks_treeview.heading('#0', text='File name')
        chunks_treeview.heading('chunks', text='Collected chunks')
        chunks_treeview.heading('lang', text='Language')

        chunks_treeview.column('#0', width=100)
        chunks_treeview.column('chunks', width=60)
        chunks_treeview.column('lang', width=40)

        chunks_treeview.pack(side=TOP, fill=X, padx=15, pady=15, expand=True)

        def logging_callback(msg: str, progress: int, result: ProcessingResult = None):
            current_import_label.config(text=msg)
            if progress > 100:
                progress_bar.config(mode='indeterminate')
            else:
                progress_bar.config(mode='determinate', value=progress)
            if result:
                chunks_treeview.insert('', index=0, 
                    text=result.source, 
                    values=(
                        len(result.chunks), 
                        get_language_name(result.lang)
                    )
                )

        def import_task():
            button_state_callback(DISABLED)
            filepaths = self._import_paths.values()
            try:
                ImportPipeline(
                    logging_callback=logging_callback,
                    reset_collections_on_import=clean_coll,
                ).import_many_documents(filepaths)
            finally:
                dialog.bell()
                button_state_callback(NORMAL)

        import_thread = threading.Thread(target=import_task)
        import_thread.start()
