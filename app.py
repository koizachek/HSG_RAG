import langsmith
from langsmith import traceable
from src.apps.chat.app import ChatbotApplication
from src.utils.logging import init_logging
from src.cache.cache import Cache
from dotenv import load_dotenv

if __name__ == "__main__":
	load_dotenv()
	Cache.configure(mode='cloud', no_cache=False)
	init_logging(interactive_mode=False)
	ChatbotApplication("de").run()

