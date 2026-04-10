from docling_core.transforms.chunker.hierarchical_chunker import ChunkingDocSerializer, ChunkingSerializerProvider
from docling_core.transforms.serializer.base   import BaseTableSerializer, SerializationResult
from docling_core.transforms.serializer.common import create_ser_result
from docling_core.types.doc.document import RichTableCell

class EnhancedTableSerializer(BaseTableSerializer):
    def serialize(self, *, item, doc_serializer, doc, **kwargs) -> SerializationResult:
        if item.self_ref in doc_serializer.get_excluded_refs(**kwargs):
            return create_ser_result(text='')

        grid = item.data.grid
        if not grid: 
            return create_ser_result(text='')
 
        row_cells = []
        for row in grid:
            clean_row = []
            for cell in row:
                if isinstance(cell, RichTableCell):
                    ser = doc_serializer.serialize(item=cell.ref.resolve(doc), **kwargs)
                    clean_row.append(ser.text.strip())
                else:
                    clean_row.append((cell.text or "").strip())
            if any(c for c in clean_row): 
                row_cells.append(clean_row)

        headers = row_cells[0]
        data_rows = row_cells[1:]

        lines = []

        for row in data_rows:
            if len(row) < 2 or not row[0].strip():
                continue

            main_key = row[0].strip().replace('\n', ' ')
            top_line = f'- {main_key}:'
            lines.append(top_line)

            for i in range(1, len(row)):
                value = row[i].strip().replace('\n', ' ')
                if not value: continue
                sub_header = headers[i].strip().replace('\n', ' ') if i < len(headers) else f""
                sub_line = f'  - {sub_header}: {value}'
                lines.append(sub_line)

            lines.append("")

        final_text = "\n".join(lines).rstrip() 
        return create_ser_result(text=final_text, span_source=item)


class EnhansedSerializerProvider(ChunkingSerializerProvider):
    def get_serializer(self, doc):
        return ChunkingDocSerializer(
            doc=doc,
            table_serializer=EnhancedTableSerializer(),
        )
