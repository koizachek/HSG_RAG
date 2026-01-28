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
        
        # ====================== Helper functions ======================
        def update_treeview():
            for item in self.files_treeview.get_children():
                self.files_treeview.delete(item)
            for filename in self._import_paths:
                self.files_treeview.insert("", 0, text=filename)

        def open_file_dialog():
            filepaths = filedialog.askopenfilenames(
                title="Select files to import",
                filetypes=(("PDF", "*.pdf"), ("Text files", "*.txt"), ("All files", "*.*"))
            )
            for path in filepaths:
                filename = os.path.basename(path)
                self._import_paths[filename] = path
            update_treeview()

        def remove_files():
            selection = self.files_treeview.selection()
            if not selection:
                return
            for item in selection:
                filename = self.files_treeview.item(item)["text"]
                self._import_paths.pop(filename, None)
            update_treeview()

        def change_button_state(state):
            add_button.config(state=state)
            remove_button.config(state=state)
            import_button.config(state=state)

        # Configure grid for 50/50 split
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)

        # ====================== LEFT SIDE ======================
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, sticky='nsew', padx=(10, 5), pady=10)

        # Button row for add/remove
        btn_row = ttk.Frame(left_frame)
        btn_row.pack(fill=X, pady=(0, 8))

        add_button = ttk.Button(btn_row, text="Add files", command=open_file_dialog)
        add_button.pack(side=LEFT, padx=8)

        remove_button = ttk.Button(btn_row, text="Remove files", command=remove_files)
        remove_button.pack(side=LEFT, padx=8)

        # Controls row for checkbox and import button
        controls_row = ttk.Frame(left_frame)
        controls_row.pack(fill=X, pady=(0, 8))

        import_button = ttk.Button(
            controls_row, 
            text="Begin Import", 
            command=lambda: self._import_callback(change_button_state)
        )
        import_button.pack(side=LEFT, padx=10)
        
        self.reset_cd_var = BooleanVar(value=False)
        reset_cb = ttk.Checkbutton(
            controls_row, 
            text="Reset database", 
            variable=self.reset_cd_var
        )
        reset_cb.pack(side=LEFT, padx=8, pady=6)

        # Files treeview
        self.files_treeview = ttk.Treeview(
            left_frame,
            columns=[],
            show="tree headings",
            selectmode="extended",
            height=18
        )
        self.files_treeview.heading("#0", text="File name")
        self.files_treeview.column("#0", width=260) 
        self.files_treeview.pack(fill=BOTH, expand=True, pady=8)

        # ====================== RIGHT SIDE ======================
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 10), pady=10)

        ttk.Label(right_frame, text="Enter URLs (one per line):").pack(anchor=W, padx=5, pady=(0, 6))

        self.url_text = Text(right_frame, width=28, height=22, undo=True, wrap="word", font=("Segoe UI", 10)) 
        self.url_text.pack(side=LEFT, fill=BOTH, expand=True, padx=5, pady=5)

        # Scrollbar
        scrollbar = ttk.Scrollbar(right_frame, orient="vertical", command=self.url_text.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.url_text.config(yscrollcommand=scrollbar.set)

        return main_frame


    def _import_callback(self, button_state_callback):
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
                pipeline = ImportPipeline(
                    logging_callback=logging_callback,
                    reset_collections_on_import=self.reset_cd_var.get(),
                )
                pipeline.import_documents(filepaths)
                pipeline.scrape(self._urls)
            finally:
                dialog.bell()
                button_state_callback(NORMAL)

        import_thread = threading.Thread(target=import_task)
        import_thread.start()
