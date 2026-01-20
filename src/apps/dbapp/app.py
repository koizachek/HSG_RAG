import os, shutil

from tkinter import *
from tkinter import ttk
from src.database.weavservice import WeaviateService
from src.apps.dbapp.utilclasses import BackupData
from config import WeaviateConfiguration as wvtconf

class DatabaseApplication:
    def __init__(self) -> None:
        self._root = self._init_root()
        
        self._backups = self._load_backup_files()
        self._init_backups_table()

        self._service = WeaviateService()

    
    def _init_root(self):
        root = Tk()
        root.title("Database Interface")
        root.geometry("600x500")

        return root

    
    def _load_backup_files(self):
        backups = []
        os.makedirs(wvtconf.BACKUP_PATH, exist_ok=True)

        for backup_id in os.listdir(wvtconf.BACKUP_PATH):
            backups.append(BackupData(backup_id))
        
        return backups


    def _init_backups_table(self):
        tree_frame = ttk.Frame(self._root)
        tree_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        label_frame = ttk.Frame(self._root)
        label_frame.pack(fill=X, expand=True, padx=10, pady=10)

        button_frame = ttk.Frame(self._root)
        button_frame.pack(fill=X, padx=10, pady=10)

        date_reverse_sort = True
        columns = ('date', 'size')
        
        info_label = ttk.Label(label_frame, text="")

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
                value=bk['date']
            )
            for collection in bk['collections']:
                tree.insert(parent, END,
                    text=collection['name'],
                    value=collection['size'],
                )

        for backup in self._backups:
            insert_backup(backup)
        sort_by_date()
           
        def create_backup():
            backup_id = self._service._create_backup()

            backup = BackupData(backup_id)
            self._backups.append(backup)
            insert_backup(backup)

        def restore_backup():
            item_id = tree.selection()[0]
            backup = tree.item(item_id)
            
            info_label.configure(text=f"Restoring backup {backup['text']}...")
            restore_bkp_btn.state(['disabled'])
            self._service._restore_backup('backup_' + backup['text'])
            info_label.configure(text=f"Successfully restored backup {backup['text']}!")
            restore_bkp_btn.state(['!disabled'])
        
        def delete_backup():
            item_id = tree.selection()[0]
            backup = tree.item(item_id)
            
            backup_path = os.path.join(wvtconf.BACKUP_PATH, 'backup_' + backup['text'])
            shutil.rmtree(backup_path, ignore_errors=True)

            tree.delete(item_id)


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
            is_root = tree.parent(item_id) == ''
            restore_bkp_btn.state(['!disabled' if is_root else 'disabled'])
            delete_bkp_btn.state(['!disabled' if is_root else 'disabled'])
        
        tree.bind("<<TreeviewSelect>>", on_item_selection)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        info_label.pack()

        tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        create_bkp_btn.pack(side=LEFT, padx=5)
        restore_bkp_btn.pack(side=RIGHT, padx=5)
        delete_bkp_btn.pack(side=RIGHT, padx=5)

    def run(self):
        self._root.mainloop()
