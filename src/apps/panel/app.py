import gradio as gr
import os
import time

# Simulated processor
def process_documents(files, options):
    results = []
    for f, opt in zip(files, options):
        results.append(f"{os.path.basename(f.name)} processed with {opt}")
        time.sleep(0.5)
    return results

# Toggle a button state
def toggle_option(option):
    return not option

# Build a file row with buttons
def build_file_rows(files, states):
    rows = []
    with gr.Column():
        for i, f in enumerate(files):
            with gr.Row():
                gr.Markdown(f"**{os.path.basename(f.name)}**")
                chunk_btn = gr.Button("Chunk ✅" if states[i]["chunk"] else "Chunk ❌")
                summary_btn = gr.Button("Summary ✅" if states[i]["summary"] else "Summary ❌")
                embed_btn = gr.Button("Embed ✅" if states[i]["embed"] else "Embed ❌")
                # Bind click events to toggle
                chunk_btn.click(toggle_option, inputs=[states[i]["chunk"]], outputs=[states[i]["chunk"]])
                summary_btn.click(toggle_option, inputs=[states[i]["summary"]], outputs=[states[i]["summary"]])
                embed_btn.click(toggle_option, inputs=[states[i]["embed"]], outputs=[states[i]["embed"]])
            rows.append(states[i])
    return rows

# Initialize UI
with gr.Blocks() as demo:
    uploaded_files = gr.File(file_count="multiple", label="Upload Files")
    file_states = gr.State([])  # track toggle states per file
    files_section = gr.Group(visible=False)
    status_box = gr.Textbox(label="Status", interactive=False)

    def display_files(files):
        if not files:
            return gr.update(visible=False), []
        states = [{"chunk": True, "summary": False, "embed": True} for _ in files]
        rows = build_file_rows(files, states)
        return gr.update(visible=True), rows

    uploaded_files.upload(
        display_files,
        inputs=[uploaded_files],
        outputs=[files_section, file_states]
    )

demo.launch()

