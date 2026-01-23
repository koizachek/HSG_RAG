import os, shutil
from datetime import datetime

from tkinter import *
from tkinter import ttk
from src.database.weavservice import WeaviateService
from src.apps.dbapp.framebase import CustomFrameBase
from src.apps.dbapp.utilclasses import BackupData
from config import WeaviateConfiguration as wvtconf

def _load_backup_files():
    backups = []
    os.makedirs(wvtconf.BACKUP_PATH, exist_ok=True)

    for backup_id in os.listdir(wvtconf.BACKUP_PATH):
        backups.append(BackupData(backup_id))
    
    return backups

class BackupsFrame(CustomFrameBase):
    def __init__(self, parent, service: WeaviateService):
        super().__init__(parent, service)
        self._backups = _load_backup_files()

    def init(self) -> ttk.Frame:
        self._backups = _load_backup_files()
        
        main_frame = ttk.Frame(self._parent)
        main_frame.pack(fill=BOTH, expand=True)

        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        label_frame = ttk.Frame(main_frame)
        label_frame.pack(fill=X, expand=True, padx=10, pady=10)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=X, padx=10, pady=10)

        date_reverse_sort = True
        columns = ('date', 'size')
        
        info_label = ttk.Label(label_frame, text="", padding=8)
        
        def _print_label(msg, backc, forc):
            info_label.configure(text=msg, foreground=forc, background=backc)
            info_label.update_idletasks()

        def print_failure(msg: str):
            _print_label(msg, "#FFCDD2", "#B71C1C")

        def print_info(msg: str):
            _print_label(msg, "#cdedff", "#1c31b7")
        
        def print_success(msg: str):
            _print_label(msg, "#d7ffcd", "#4db71c")


        tree = ttk.Treeview(
            tree_frame,
            columns=columns, 
            show='tree headings',
            selectmode='browse',
        )
            
        def sort_by_date():
            nonlocal date_reverse_sort

            parents = tree.get_children("")
            data = []

            for p in parents:
                value = tree.set(p, 'date')
                try:
                    value = datetime.strptime(value, "%d.%m.%Y %H:%M:%S")
                except Exception:
                    pass
                data.append((value, p))

            data.sort(reverse=date_reverse_sort)
            date_reverse_sort = not date_reverse_sort

            for index, (_, p) in enumerate(data):
                tree.move(p, "", index)

            tree.heading(
                'date',      
                text='Created at    ' + ('▾' if date_reverse_sort else '▴'),     
                command=lambda: sort_by_date()
            )

        tree.heading('#0', text='Backup ID')
        tree.heading('date', text='Created at    ▾', command=lambda: sort_by_date())
        tree.heading('size', text='Embeddings amount')
        
        tree.column("#0", width=100)
        tree.column("date", width=60)
        tree.column("size", width=30)

        def insert_backup(backup):
            nonlocal date_reverse_sort
            bk = backup.to_treeformat()
            parent = tree.insert('', 0 if not date_reverse_sort else END, 
                text=bk['id'],
                values=bk['date']
            )
            for collection in bk['collections']:
                tree.insert(parent, END,
                    text=collection['name'],
                    values=collection['size'],
                )

        for backup in self._backups:
            insert_backup(backup)
        sort_by_date()
           
        def create_backup():
            print_info(f"Creating new backup...")
            backup_id = self._service._create_backup()

            backup = BackupData(backup_id)
            self._backups.append(backup)
            insert_backup(backup)
            print_success(f"Successfully created new backup {backup._backup_id}!")

        def restore_backup():
            item_id = tree.selection()[0]
            backup = tree.item(item_id)
            
            print_info(f"Restoring backup {backup['text']}...")
            self._service._restore_backup('backup_' + backup['text'])
            print_success(f"Successfully restored backup {backup['text']}!")
        
        def delete_backup():
            item_id = tree.selection()[0]
            backup = tree.item(item_id)
            
            backup_path = os.path.join(wvtconf.BACKUP_PATH, 'backup_' + backup['text'])
            shutil.rmtree(backup_path, ignore_errors=True)

            tree.delete(item_id)
            print_success(f"Deleted backup {backup['text']}.")


        create_bkp_btn = ttk.Button(
                button_frame,
                text="Create Backup", 
                command=create_backup
        )

        restore_bkp_btn = ttk.Button(
            button_frame,
            text="Restore Backup", 
            command=restore_backup,
            state=['disabled']
        )

        delete_bkp_btn = ttk.Button(
            button_frame,
            text="Delete Backup",
            command=delete_backup,
            state=['disabled']
        )

        def on_item_selection(event):
            selected = tree.selection()
            if not selected:
                restore_bkp_btn.state(['disabled'])
                delete_bkp_btn.state(['disabled'])
                return 

            item_id = selected[0]
            is_parent = tree.parent(item_id) == ''
            restore_bkp_btn.state(['!disabled' if is_parent else 'disabled'])
            delete_bkp_btn.state(['!disabled' if is_parent else 'disabled'])
        
        tree.bind("<<TreeviewSelect>>", on_item_selection)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        info_label.pack()

        tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        create_bkp_btn.pack(side=LEFT, padx=5)
        restore_bkp_btn.pack(side=RIGHT, padx=5)
        delete_bkp_btn.pack(side=RIGHT, padx=5)

        return main_frame
