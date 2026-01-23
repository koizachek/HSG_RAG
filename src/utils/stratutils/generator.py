from src.utils.stratutils.templates import *

def generate_strategy(name, prop):
    preamble = PREAMBLE_TEMPL_STD.format(name=name)
    header = f"{FUNC_HEADER_TEMPL} -> {FUNC_RETURN_TYPE_TEMPL.get(prop['data_type'], None)}:"
    body = BODY_TEMPL.get(name, BODY_TEMPL_STD)

    return f"{preamble}\n\n{header}\n{COMMENT_TEMPL_STD}\n\n{body}"
