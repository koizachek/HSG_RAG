from tkinter import *
from tkinter import ttk
from src.apps.dbapp.framebase import CustomFrameBase
from src.database.weavservice import WeaviateService

class QueryFrame(CustomFrameBase):
    def __init__(self, parent, service: WeaviateService) -> None:
        super().__init__(parent, service)

    def init(self) -> ttk.Frame:
        main_frame = ttk.Frame(self._parent)
        main_frame.pack(fill=BOTH, expand=True)

        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=X, padx=10, pady=(5, 10))

        self.language_var = StringVar(value="de")

        self.filters_button = ttk.Button(input_frame, text="Filters...", command=self.open_filters)
        self.filters_button.pack(side=LEFT, padx=(0, 10))

        lang_frame = ttk.Frame(input_frame)  
        lang_frame.pack(side=LEFT, padx=(0, 15))

        ttk.Radiobutton(
            lang_frame,
            text="EN",
            variable=self.language_var,
            value="en"
        ).pack(side=LEFT, padx=(0, 8))

        ttk.Radiobutton(
            lang_frame,
            text="DE",
            variable=self.language_var,
            value="de"
        ).pack(side=LEFT)

        self.query_entry = ttk.Entry(input_frame)
        self.query_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 10))

        self.send_button = ttk.Button(input_frame, text="Send", command=self.send_query)
        self.send_button.pack(side=RIGHT)

        self.query_entry.bind("<Return>", lambda _: self.send_query())

        results_frame = ttk.Frame(main_frame)
        results_frame.pack(fill=BOTH, expand=True, padx=10, pady=(10, 5))

        self.results_text = Text(results_frame, wrap=WORD, font=("TkDefaultFont", 10))
        y_scrollbar = ttk.Scrollbar(results_frame, orient=VERTICAL, command=self.results_text.yview)
        self.results_text.configure(yscrollcommand=y_scrollbar.set)

        self.results_text.pack(side=LEFT, fill=BOTH, expand=True)
        y_scrollbar.pack(side=RIGHT, fill=Y)

        self.results_text.config(state=NORMAL)
        self.results_text.insert(END, "Enter your query below and click Send (or press Enter) to see results.\n")
        self.results_text.config(state=DISABLED)
 
        return main_frame


    def send_query(self):
        query_text = self.query_entry.get().strip()
        if not query_text:
            return

        self.query_entry.delete(0, END)

        try:
            response, _ = self._service.query(
                lang=self.language_var.get(),
                query=query_text,
            )
            result_str = ''.join([f"""
---------------------- Result {idx} ----------------------
SOURCE: {obj.properties['source']}
INSERTION DATE: {obj.properties['date']}
RELEVANT PROGRAMS: {', '.join(obj.properties['programs'])}

CONTENT: 
{obj.properties['body']}
""" for idx, obj in enumerate(response.objects, start=1)])

            result_str = f"Query: {query_text}\n{result_str}"

            self.display_result(result_str)
        except Exception as e:
            self.display_result(f"Error:\n{str(e)}")


    def display_result(self, result_text: str):
        self.results_text.config(state=NORMAL)
        self.results_text.delete(1.0, END)
        self.results_text.insert(END, result_text + "\n")
        self.results_text.config(state=DISABLED)
        self.results_text.see(1.0)


    def open_filters(self):
        dialog = Toplevel(self._parent)
        dialog.title("Query Filters")
        dialog.geometry("400x300")
        dialog.grab_set()
