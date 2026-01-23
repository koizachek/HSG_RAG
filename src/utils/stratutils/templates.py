FUNC_HEADER_TEMPL = "def run(file_name: str, file_content: str, chunk: str)"

FUNC_RETURN_TYPE_TEMPL = {
    "text": "str",
    "date": "str",
    "text[]": "list[str]",
}

PREAMBLE_TEMPL_STD="""\"\"\"Property extraction strategy for property {name}.\"\"\""""

COMMENT_TEMPL_STD = """\t\"\"\"
\tRuns the property extraction strategy on processed chunk.

\tArgs:
\t\tfile_name (str): Name of the file from which the chunk was collected.
\t\tfile_content (str): Entire text extracted from file.
\t\tchunk (str): Chunk collected from file.
    
\tReturns:
\t\tExtracted property.
\t\"\"\""""

BODY_TEMPL_STD = "\treturn chunk"

BODY_TEMPL = {
    'body':        "\treturn chunk",
    'source':      "\treturn file_name",
    'chunk_id':    "\timport hashlib\n\treturn hashlib.md5(chunk.strip().encode('utf-8')).hexdigest()",
    'document_id': "\timport hashlib\n\treturn hashlib.md5(file_content.strip().encode('utf-8')).hexdigest()",
    'date':        "\timport datetime\n\treturn datetime.datetime.now().replace(tzinfo=datetime.timezone.utc)"
}
