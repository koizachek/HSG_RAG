import os, json

from tkinter import *
from tkinter import ttk
from src.apps.dbapp.framebase import CustomFrameBase
from src.utils.stratutils.generator import generate_strategy
from src.database.weavservice import WeaviateService
from config import WeaviateConfiguration as wvtconf

def _dump_schema(schema):
    os.makedirs(wvtconf.PROPERTIES_PATH, exist_ok=True)
    properties_file_path = os.path.join(wvtconf.PROPERTIES_PATH, 'properties.json')
    with open(properties_file_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, default=str)


class SchemaConfigurationFrame(CustomFrameBase):
    def __init__(self, parent, service: WeaviateService) -> None:
        super().__init__(parent, service)
        self._schema = self._load_schema_data()
        self._strategies = self._load_strategies()
    

    def _load_strategies(self) -> dict:
        os.makedirs(wvtconf.STRATEGIES_PATH, exist_ok=True)
        loaded_strats = os.listdir(wvtconf.STRATEGIES_PATH)
        strategies = {}

        for name, prop in self._schema.items():
            strategy_file = f"strat_{name}.py"
            file_path = os.path.join(wvtconf.STRATEGIES_PATH, strategy_file)
            strategy_content = ""
            
            if strategy_file not in loaded_strats:
                strategy_content = generate_strategy(name, prop)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(strategy_content)
            else:
                with open(file_path) as f:
                    strategy_content = f.read()

            strategies[name] = strategy_content

        return strategies


    def _save_strategy(self, name, strategy) -> None:
        os.makedirs(wvtconf.STRATEGIES_PATH, exist_ok=True)
        self._strategies[name] = strategy

        file_path = os.path.join(wvtconf.STRATEGIES_PATH, f"strat_{name}.py")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(strategy)


    def _load_schema_data(self) -> dict:
        schema = self._service._extract_data()['schema'][0]
        
        schema_data = {}

        for prop in schema['properties']:
            data_property = {
                'description': prop.get('description', ''),
                'data_type': prop['dataType'][0],
                'filterable': prop['indexFilterable'],
                'searchable': prop['indexSearchable'],
                'skip_vectorization': prop['moduleConfig']['text2vec-huggingface']['skip'],
            }
            schema_data[prop['name']] = data_property
        
        _dump_schema(schema_data)

        return schema_data


    def _update_schema_property(self, old_name: str, new_name: str, prop: dict) -> None:
        del self._schema[old_name]
        self._schema[new_name] = prop  
        _dump_schema(self._schema)


    def _add_schema_property(self, name, prop: dict) -> None:
        self._schema[name] = prop 
        _dump_schema(self._schema)


    def _delete_schema_property(self, name) -> None:
        del self._schema[name]
        _dump_schema(self._schema)


    def init(self) -> ttk.Frame:
        main_frame = ttk.Frame(self._parent)
        main_frame.pack(fill=BOTH, expand=True)

        schema_frame = ttk.Frame(main_frame)
        schema_frame.pack(fill=BOTH, expand=True)
        
        add_button = ttk.Button(schema_frame, text='Add property', 
                                command=lambda: self._add_property(refresh_table))
        add_button.pack(anchor=NW, padx=5, pady=5)

        canvas = Canvas(schema_frame)
        scrollbar = ttk.Scrollbar(schema_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        def refresh_table():
            for widget in scrollable_frame.winfo_children():
                widget.destroy()

            self._build_table(scrollable_frame, refresh_table)
        
        refresh_table() 
        return main_frame


    def _build_table(self, parent_frame, refresh_callback):
        style = ttk.Style()
        style.configure('Header.TLabel', font=('Helvetica', 10, 'bold'), background='#e0e0e0')
        style.configure('EvenRow.TLabel', background='#f0f0f0')
        style.configure('OddRow.TLabel', background='white')

        table_frame = ttk.Frame(parent_frame)
        table_frame.pack(fill=X, padx=5, pady=5)

        for i in range(5):
            table_frame.grid_columnconfigure(i, minsize=100, weight=1) 

        headers = ['Name', 'Data Type', 'Filterable', 'Searchable', 'Skip Vectorize']
        for col, text in enumerate(headers):
            label = ttk.Label(table_frame, text=text, borderwidth=1, relief=SOLID, anchor='center', style='Header.TLabel')
            label.grid(row=0, column=col, sticky='ew')

        for idx, (name, prop) in enumerate(self._schema.items(), start=1):
            row_style = 'EvenRow.TLabel' if idx % 2 == 0 else 'OddRow.TLabel'
            
            row_name_label = ttk.Label(table_frame, text=name, style=row_style)
            row_type_label = ttk.Label(table_frame, text=prop['data_type'].upper(), style=row_style)
            row_filterable_label = ttk.Label(table_frame, text='Yes' if prop['filterable'] else 'No', style=row_style)
            row_searchable_label = ttk.Label(table_frame, text='Yes' if prop['searchable'] else 'No', style=row_style)
            row_vectorize_label = ttk.Label(table_frame, text='Yes' if prop['skip_vectorization'] else 'No', style=row_style)
            
            row_edit_button = ttk.Button(table_frame, text='Edit', 
                command=lambda n=name, p=prop: self._edit_property(n, p, refresh_callback))
            row_delete_button = ttk.Button(table_frame, text='Delete', 
                command=lambda n=name: self._delete_property(n, refresh_callback))
            row_strategy_button = ttk.Button(table_frame, text='Strategy', 
                command=lambda n=name: self._handle_strategy(n)) 

            row_name_label.grid(row=idx, column=0, sticky='ew', ipadx=25)
            row_type_label.grid(row=idx, column=1, sticky='ew', ipadx=25)
            row_filterable_label.grid(row=idx, column=2, sticky='ew', ipadx=25)
            row_searchable_label.grid(row=idx, column=3, sticky='ew')
            row_vectorize_label.grid(row=idx, column=4, sticky='ew')
            row_edit_button.grid(row=idx, column=5, sticky='ew')
            row_delete_button.grid(row=idx, column=6, sticky='ew')
            row_strategy_button.grid(row=idx, column=7, sticky='ew')
    
    
    def _handle_strategy(self, n):
        dialog = Toplevel()
        dialog.title(f"Property {n} strategy")
        dialog.geometry("700x400")

        field_frame = ttk.Frame(dialog)
        field_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)  

        scrollbar = Scrollbar(field_frame, orient=VERTICAL)
        scrollbar.pack(side=RIGHT, fill=Y)

        strategy = self._strategies[n]
        edit_field = Text(field_frame, width=80, height=15, wrap=WORD, yscrollcommand=scrollbar.set)  
        edit_field.insert(END, strategy)
        edit_field.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar.config(command=edit_field.yview)  

        def commit():
            new_strategy = edit_field.get("1.0", END).strip()  
            self._save_strategy(n, new_strategy) 
            dialog.destroy()  

        
        ttk.Button(dialog, text="Save", command=commit).pack(side=BOTTOM, anchor=S, pady=10)

    
    def _delete_property(self, name, refresh_callback):
        msg = f"Do you want to delete property '{name}'?"
        dialog = Toplevel()
        dialog.title('Warning!')
        dialog.geometry(f"{len(msg)*5+120}x50")
        dialog.grab_set()

        ttk.Label(dialog, text=msg).pack()
        
        def submit():
            self._delete_schema_property(name)
            refresh_callback()
            dialog.destroy()
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=X, expand=True)

        ttk.Button(button_frame, text='Delete', command=submit).pack(side=LEFT, padx=15)
        ttk.Button(button_frame, text='Cancel', command=dialog.destroy).pack(side=RIGHT, padx=15) 


    def _add_property(self, refresh_callback):
        dialog = Toplevel()
        dialog.title(f"New property")
        dialog.geometry("280x300") 
        dialog.grab_set() 

        texts_frame = ttk.Frame(dialog)
        texts_frame.pack(fill=X, expand=True)

        ttk.Label(texts_frame, text="Name:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        name_entry = ttk.Entry(texts_frame)
        name_entry.grid(row=0, column=1, padx=5, pady=5, sticky='w')

        ttk.Label(texts_frame, text="Description:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        desc_entry = ttk.Entry(texts_frame)
        desc_entry.insert(0, '') 
        desc_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')

        ttk.Label(texts_frame, text="Data Type:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        type_var = StringVar(value='text')
        type_combo = ttk.Combobox(texts_frame, textvariable=type_var, 
            values=["text", "int", "number", "boolean", "date", "text[]", "int[]", "number[]", "boolean[]", "date[]", "object"]
        )      
        type_combo.grid(row=2, column=1, padx=5, pady=5, sticky='w')
        
        checks_frame = ttk.Frame(dialog)
        checks_frame.pack(fill=X, expand=True)

        filterable_var = BooleanVar(value=True)
        searchable_var = BooleanVar(value=True)
        skip_vec_var = BooleanVar(value=False)

        ttk.Checkbutton(checks_frame, text="Filterable        ", variable=filterable_var).pack(anchor=W, padx=15)
        ttk.Checkbutton(checks_frame, text="Searchable        ", variable=searchable_var).pack(anchor=W, padx=15)
        ttk.Checkbutton(checks_frame, text="Skip Vectorization", variable=skip_vec_var).pack(anchor=W, padx=15)   
        
        def submit():
            name = name_entry.get()
            if not name:
                self._show_messagebox("Parameter 'name' is required!")
                return
            if name in self._schema.keys():
                self._show_messagebox(f"Property with name '{name}' already exists!")
                return

            prop = {
                'description': desc_entry.get().strip(),
                'data_type': type_var.get(),
                'filterable': filterable_var.get(),
                'searchable': searchable_var.get(),
                'skip_vectorization': skip_vec_var.get(),
            }

            self._add_schema_property(name, prop)
            refresh_callback()
            dialog.destroy()

        buttons_frame = ttk.Frame(dialog)
        buttons_frame.pack(fill=X, expand=True)

        ttk.Button(buttons_frame, text="Save", command=submit).pack(side=LEFT, padx=15)    
        ttk.Button(buttons_frame, text="Cancel", command=dialog.destroy).pack(side=RIGHT, padx=15)


    def _edit_property(self, name: str, prop: dict, refresh_callback):
        dialog = Toplevel()
        dialog.title(f"Edit Property: {name}")
        dialog.geometry("280x300") 
        dialog.grab_set() 

        texts_frame = ttk.Frame(dialog)
        texts_frame.pack(fill=X, expand=True)

        ttk.Label(texts_frame, text="Name:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        name_entry = ttk.Entry(texts_frame)
        name_entry.insert(0, name)
        name_entry.grid(row=0, column=1, padx=5, pady=5, sticky='w')

        ttk.Label(texts_frame, text="Description:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        desc_entry = ttk.Entry(texts_frame)
        desc_entry.insert(0, prop.get('description', '')) 
        desc_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')

        ttk.Label(texts_frame, text="Data Type:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        type_var = StringVar(value=prop['data_type'])
        type_combo = ttk.Combobox(texts_frame, textvariable=type_var, 
            values=["text", "int", "number", "boolean", "date", "text[]", "int[]", "number[]", "boolean[]", "date[]", "object"]
        )      
        type_combo.grid(row=2, column=1, padx=5, pady=5, sticky='w')
        
        checks_frame = ttk.Frame(dialog)
        checks_frame.pack(fill=X, expand=True)

        filterable_var = BooleanVar(value=prop['filterable'])
        searchable_var = BooleanVar(value=prop['searchable'])
        skip_vec_var = BooleanVar(value=prop['skip_vectorization'])

        ttk.Checkbutton(checks_frame, text="Filterable        ", variable=filterable_var).pack(anchor=W, padx=15)
        ttk.Checkbutton(checks_frame, text="Searchable        ", variable=searchable_var).pack(anchor=W, padx=15)
        ttk.Checkbutton(checks_frame, text="Skip Vectorization", variable=skip_vec_var).pack(anchor=W, padx=15)

        def submit():
            new_name = name_entry.get().strip()
            if not new_name:
                self._show_messagebox("Parameter 'name' is required!")
                return
            
            updated_prop = {
                'description': desc_entry.get().strip(),
                'data_type': type_var.get(),
                'filterable': filterable_var.get(),
                'searchable': searchable_var.get(),
                'skip_vectorization': skip_vec_var.get(),
            }
            
            self._update_schema_property(name, new_name, updated_prop)
            refresh_callback()
            dialog.destroy()

        buttons_frame = ttk.Frame(dialog)
        buttons_frame.pack(fill=X, expand=True)

        ttk.Button(buttons_frame, text="Save", command=submit).pack(side=LEFT, padx=15)    
        ttk.Button(buttons_frame, text="Cancel", command=dialog.destroy).pack(side=RIGHT, padx=15)


    @staticmethod
    def _show_messagebox(msg):
        dialog = Toplevel()
        dialog.title('Warning!')
        dialog.geometry(f"{len(msg)*5+120}x50")
        dialog.grab_set()

        ttk.Label(dialog, text=msg).pack()
        ttk.Button(dialog, text='OK', command=dialog.destroy).pack(padx=15)
