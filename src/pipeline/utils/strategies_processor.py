import os, re, importlib.util 
from dataclasses import dataclass

from src.config import config
from src.utils.logging import get_logger

logger = get_logger('pipeline.strats')

@dataclass
class StrategyArguments:
    name:    str  = None 
    content: str  = None 
    chunk:   str  = None

class StrategiesProcessor:
    def __init__(self) -> None: 
        os.makedirs(config.weaviate.STRATEGIES_PATH, exist_ok=True)

        self._strategies: dict = self._load_strategies() 
    
    def list_strategies(self) -> list[str]:
        return self._strategies.keys()

    def apply_strategy(self, strategy_name: str, arguments: StrategyArguments | dict):
        if strategy_name not in self._strategies.keys():
            raise ValueError(f"Cannot apply strategy '{strategy_name}': strategy not found!")
        
        try:
            strategy = self._strategies[strategy_name]
            run_result = None
            if isinstance(arguments, StrategyArguments):
                run_result = strategy.run(arguments.name, arguments.content, arguments.chunk)
            else:
                run_result = strategy.run(
                    arguments.get('document_name', ""), 
                    arguments.get('document_content', ""),
                    arguments.get('chunk', None)
            )
            return run_result
        except Exception as e:
            raise RuntimeError(f"Cannot apply strategy '{strategy_name}': {e}")


    def _load_strategies(self) -> dict:
        loaded_strategies = dict()
        for strat_file in os.listdir(config.weaviate.STRATEGIES_PATH):
            strat_name = self._extract_strategy_name(strat_file)
            if not strat_name: continue 

            strat_path = os.path.join(config.weaviate.STRATEGIES_PATH, strat_file)

            spec = importlib.util.spec_from_file_location(
                name=strat_name,
                location=strat_path
            )
            strategy = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(strategy)

            if not hasattr(strategy, 'run'):
                logger.warning(f"Found strategy '{strat_name}' has no valid run() function!")
                continue

            loaded_strategies[strat_name] = strategy
            
        logger.info(f"Loaded {len(loaded_strategies.keys())} strategies")
        return loaded_strategies


    def _extract_strategy_name(self, strat_file: str) -> str:
        match = re.fullmatch(r'^strat_(.*)\.py$', strat_file)
        return match.group(1) if match else None
                
        

