import os
import gradio as gr
from src.rag.agent_chain import ExecutiveAgentChain 
from src.utils.logging import get_logger, cached_log_handler

logger = get_logger("chatbot_app")

CSS_PATH = "frontend/style.css"

DE_BOT_PROMPTS = ['Welches Programm passt zu meinem persönlichen Hintergrund?',
                  'Was sind die Unterschiede zwischen den drei Programmen?',
                  'Welche Voraussetzungen muss ein Bewerber erfüllen?']

EN_BOT_PROMPTS = ['What program suits my personal background?',
                  'What are the differences between all three programs?',
                  'Which requirements does an applicant has to fulfill?']

BOT_PROMPTS = {'de': DE_BOT_PROMPTS,
               'en': EN_BOT_PROMPTS}


class ChatbotApplication:
    def __init__(self, language: str = 'de') -> None:
        self._app = gr.Blocks()       
        
        with self._app:
            # Initial state variables
            agent_state = gr.State(None)
            
            lang_storage = gr.BrowserState(language)
            chat_storage = gr.BrowserState(None)
            msg_box_storage = gr.BrowserState(None)
             
            reset_button = gr.Button("Reset Conversation")
            
            with gr.Column():
                #Title
                gr.Markdown("## Executive Education Adviser", elem_id="title")
                
                # Prompt suggestions
                with gr.Row():
                    prompt_buttons = [
                        gr.Button(label) for label in BOT_PROMPTS[language.lower()]
                    ]

                # Chat area
                with gr.Column():
                    msg_box = gr.Textbox(container=False, submit_btn=True)
                    chatbot = gr.Chatbot(show_label=False)
                    chat_interface = gr.ChatInterface(
                        fn=lambda msg, history, agent: self._chat( 
                            message=msg,
                            history=history,
                            agent=agent,
                        ),
                        chatbot=chatbot,
                        textbox=msg_box,
                        additional_inputs=[agent_state],
                        #title="Executive Education Adviser",
                        #type='messages',
                    )

                    lang_selector = gr.Radio(
                        choices=["DE", "EN"],
                        value=language.upper(),
                        interactive=True,
                        show_label=False,
                        container=False,
                        elem_id="lang-toggle",
                    )

            
            def clear_chat_immediate():
                return [], None
            
            def on_lang_change(language):
                lang_code = language.lower()
                return switch_language(lang_code)
            
            def initalize_agent(language):
                agent = ExecutiveAgentChain(language=language)
                greeting = agent.generate_greeting()
                return agent, [text_msg("assistant", greeting)]
            
            def init_session(saved_lang, saved_chat, saved_msg_text):
                # init agent
                lang = (saved_lang or language).lower()
                agent = ExecutiveAgentChain(language=lang)
               
                # Load chat history
                if saved_chat is not None and len(saved_chat) > 0:
                    history = saved_chat
                else:
                    greeting = agent.generate_greeting()
                    history = [text_msg("assistant", greeting)]
                
                # Get prompt buttons labels
                labels_prompt_btns = BOT_PROMPTS[lang]
                
                # Load message box text
                msg_box_text = saved_msg_text or ""

                return agent, lang.upper(), history, *labels_prompt_btns, msg_box_text

            def switch_language(new_language):
                new_agent, greeting = initalize_agent(new_language)
                return (
                    new_agent,
                    new_language,
                    greeting,
                )
            
            def pick_prompt(lang, prompt_idx):
                return BOT_PROMPTS[lang.lower()][prompt_idx]

            def change_lang_of_prompts(selected_lang):
                return BOT_PROMPTS[selected_lang.lower()]
            
            def text_msg(role: str, text: str):
                return {"role": role, "content": [{"type": "text", "text": text}]}

            lang_selector.input(fn=clear_chat_immediate, outputs=[chat_interface.chatbot, chat_storage], queue=True)
            lang_selector.input(fn=on_lang_change, inputs=[lang_selector], outputs=[agent_state, lang_storage, chat_interface.chatbot], queue=True)
            lang_selector.input(fn=change_lang_of_prompts, inputs=[lang_selector], outputs=prompt_buttons, queue=True)

            reset_button.click(fn=clear_chat_immediate, outputs=[chat_interface.chatbot, chat_storage], queue=True)
            reset_button.click(fn=switch_language, inputs=[lang_storage], outputs=[agent_state, lang_storage, chat_interface.chatbot], queue=True)
            
            for idx, btn in enumerate(prompt_buttons):
                btn.click(fn=pick_prompt, inputs=[lang_storage, gr.State(idx)], outputs=[msg_box], queue=True)

            @gr.on([msg_box.change], inputs=[msg_box], outputs=[msg_box_storage])
            def save_msg_box_to_chat_storage(msg_box_text):
                return msg_box_text

            @gr.on([chat_interface.chatbot.change], inputs=[chat_interface.chatbot], outputs=[chat_storage])
            def save_chat_to_chat_storage(curr_chat):
                return curr_chat

            self._app.load(
                fn=init_session,
                inputs=[lang_storage, chat_storage, msg_box_storage],
                outputs=[agent_state, lang_selector, chat_interface.chatbot, *prompt_buttons, msg_box],
            )

    @property
    def app(self) -> gr.Blocks:
        """Expose underlying Gradio Blocks for external runners (e.g., HF Spaces)."""
        return self._app

    def _chat(self, message: str, history: list[dict], agent: ExecutiveAgentChain):
       if agent is None:
           logger.error("Agent not initialized")
           return ["I apologize, but the chatbot is not properly initialized. Please refresh the page or contact support."]
       
       answers = []
       try:
           # Log user input
           logger.info(f"Processing user query: {message[:100]}...")
           
           # Query agent (now includes input handling, scope checking, and formatting)
           response = agent.query(query=message)
           
           logger.info(f"Received and formatted response from agent ({len(response)} chars)")
           answers.append(response)
           
       except Exception as e:
           logger.error(f"Error processing query: {e}", exc_info=True)
           
           # Provide helpful error message instead of empty string
           error_message = (
               "I apologize, but I encountered an error processing your request. "
               "Please try rephrasing your question or contact our admissions team for assistance."
           )
           answers.append(error_message)
       
       return answers


    def run(self):
        self._app.launch(
            share=os.getenv("GRADIO_SHARE", "false").lower() == "true",
            server_name=os.getenv("SERVER_NAME", "0.0.0.0"),
            server_port=int(os.getenv("PORT", 7860)),
            css_paths=[CSS_PATH] if os.path.exists(CSS_PATH) else None,
        )
