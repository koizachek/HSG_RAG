"""Property extraction strategy for property source."""

def run(file_name: str, file_content: str, chunk: str) -> str:
	"""
	Runs the property extraction strategy on processed chunk.

	Args:
		file_name (str): Name of the file from which the chunk was collected.
		file_content (str): Entire text extracted from file.
		chunk (str): Chunk collected from file.
    
	Returns:
		Extracted property.
	"""

	return file_name