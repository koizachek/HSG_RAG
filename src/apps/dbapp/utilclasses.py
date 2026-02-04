import os, json 
from datetime import datetime
from src.config import config 

class BackupData:
    def __init__(self, backup_id: str) -> None:
        self._backup_id = backup_id
        self._creation_date = ""
        self._collections = []

        backup_path = os.path.join(config.weaviate.BACKUP_PATH, backup_id)
        files = os.listdir(backup_path)

        if 'data.json' in files:
            data_path = os.path.join(backup_path, 'data.json')
            with open(data_path) as f:
                data = json.load(f)

                date = datetime.fromisoformat(data['creation_date'])
                self._creation_date = date.strftime("%d.%m.%Y %H:%M:%S")
        
        if 'objects.json' in files:
            objects_path = os.path.join(backup_path, 'objects.json')
            with open(objects_path) as f:
                data = json.load(f)
                for name, objs in data.items():
                    self._collections.append({
                        'name': name.lower(),
                        'size': ('', len(objs))
                    }) 


    def to_treeformat(self):
        return {
            'id': self._backup_id.replace('backup_', ''),
            'date': (self._creation_date, ''),
            'collections': self._collections,      
        }
