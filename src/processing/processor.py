"""
Data processor for cleaning and structuring scraped program data.
"""
import json
import logging
import os
from typing import Dict, List, Any

import pandas as pd

from config import RAW_DATA_PATH, PROCESSED_DATA_PATH

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class DataProcessor:
    """Processor for cleaning and structuring scraped program data."""

    def __init__(self, input_path: str = RAW_DATA_PATH, output_path: str = PROCESSED_DATA_PATH, manual_data_path: str = None):
        """
        Initialize the data processor.

        Args:
            input_path: Path to the raw data file.
            output_path: Path to save the processed data.
            manual_data_path: Path to the manual data file (optional).
        """
        self.input_path = input_path
        self.output_path = output_path
        self.manual_data_path = manual_data_path or os.path.join(os.path.dirname(input_path), "manual_data.json")

    def load_data(self) -> List[Dict[str, Any]]:
        """
        Load raw data from the input file.

        Returns:
            A list of dictionaries containing program data.
        """
        try:
            with open(self.input_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # If raw data is empty, try to load manual data
            if not data and os.path.exists(self.manual_data_path):
                logger.info(f"Raw data is empty, loading manual data from {self.manual_data_path}")
                with open(self.manual_data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info(f"Loaded {len(data)} programs from {self.manual_data_path}")
            else:
                logger.info(f"Loaded {len(data)} programs from {self.input_path}")
            
            return data
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            
            # If there was an error, try to load manual data as a fallback
            try:
                if os.path.exists(self.manual_data_path):
                    logger.info(f"Attempting to load manual data from {self.manual_data_path}")
                    with open(self.manual_data_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    logger.info(f"Loaded {len(data)} programs from {self.manual_data_path}")
                    return data
            except Exception as e2:
                logger.error(f"Error loading manual data: {e2}")
            
            return []

    def save_data(self, data: List[Dict[str, Any]]) -> None:
        """
        Save processed data to the output file.

        Args:
            data: The processed data to save.
        """
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
            
            with open(self.output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Saved {len(data)} processed programs to {self.output_path}")
        except Exception as e:
            logger.error(f"Error saving data to {self.output_path}: {e}")

    def clean_text(self, text: str) -> str:
        """
        Clean text by removing extra whitespace and normalizing.

        Args:
            text: The text to clean.

        Returns:
            The cleaned text.
        """
        if not text or not isinstance(text, str):
            return ""
        
        # Replace multiple whitespace with a single space
        cleaned = " ".join(text.split())
        return cleaned.strip()

    def clean_list(self, items: List[str]) -> List[str]:
        """
        Clean a list of text items.

        Args:
            items: The list of text items to clean.

        Returns:
            The cleaned list of text items.
        """
        if not items or not isinstance(items, list):
            return []
        
        cleaned_items = [self.clean_text(item) for item in items if item]
        return [item for item in cleaned_items if item]  # Remove empty items

    def normalize_costs(self, cost_text: str) -> Dict[str, Any]:
        """
        Normalize cost information.

        Args:
            cost_text: The cost text to normalize.

        Returns:
            A dictionary with normalized cost information.
        """
        if not cost_text or cost_text == "Not specified":
            return {"amount": None, "currency": None, "original_text": cost_text}
        
        # Try to extract currency and amount
        import re
        
        # Look for common currency patterns
        currency_patterns = {
            "CHF": r"CHF\s*([\d\',\.]+)",
            "EUR": r"(?:€|EUR)\s*([\d\',\.]+)",
            "USD": r"(?:\$|USD)\s*([\d\',\.]+)",
        }
        
        for currency, pattern in currency_patterns.items():
            match = re.search(pattern, cost_text, re.IGNORECASE)
            if match:
                # Extract the amount and clean it
                amount_str = match.group(1)
                # Remove thousands separators and convert to float
                amount_str = amount_str.replace(",", "").replace("'", "")
                try:
                    amount = float(amount_str)
                    return {
                        "amount": amount,
                        "currency": currency,
                        "original_text": cost_text,
                    }
                except ValueError:
                    pass
        
        # If no pattern matched, return the original text
        return {"amount": None, "currency": None, "original_text": cost_text}

    def normalize_duration(self, duration_text: str) -> Dict[str, Any]:
        """
        Normalize duration information.

        Args:
            duration_text: The duration text to normalize.

        Returns:
            A dictionary with normalized duration information.
        """
        if not duration_text or duration_text == "Not specified":
            return {"months": None, "original_text": duration_text}
        
        # Try to extract duration in months
        import re
        
        # Look for common duration patterns
        month_patterns = [
            r"(\d+)\s*months?",
            r"(\d+)\s*month program",
        ]
        
        year_patterns = [
            r"(\d+)\s*years?",
            r"(\d+)\s*year program",
            r"(\d+)\s*-\s*year",
        ]
        
        # Check for months first
        for pattern in month_patterns:
            match = re.search(pattern, duration_text, re.IGNORECASE)
            if match:
                try:
                    months = int(match.group(1))
                    return {
                        "months": months,
                        "original_text": duration_text,
                    }
                except ValueError:
                    pass
        
        # Check for years and convert to months
        for pattern in year_patterns:
            match = re.search(pattern, duration_text, re.IGNORECASE)
            if match:
                try:
                    years = int(match.group(1))
                    months = years * 12
                    return {
                        "months": months,
                        "original_text": duration_text,
                    }
                except ValueError:
                    pass
        
        # If no pattern matched, return the original text
        return {"months": None, "original_text": duration_text}

    def process_program(self, program: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single program's data.

        Args:
            program: The program data to process.

        Returns:
            The processed program data.
        """
        processed = {}
        
        # Copy basic fields
        processed["url"] = program.get("url", "")
        processed["name"] = self.clean_text(program.get("name", "Unknown Program"))
        processed["description"] = self.clean_text(program.get("description", ""))
        
        # Process duration
        processed["duration"] = self.normalize_duration(program.get("duration", "Not specified"))
        
        # Process costs
        processed["costs"] = self.normalize_costs(program.get("costs", "Not specified"))
        
        # Process lists
        processed["curriculum"] = self.clean_list(program.get("curriculum", []))
        processed["admission_requirements"] = self.clean_list(program.get("admission_requirements", []))
        
        # Process faculty
        faculty = program.get("faculty", [])
        processed_faculty = []
        for member in faculty:
            if isinstance(member, dict):
                processed_faculty.append({
                    "name": self.clean_text(member.get("name", "")),
                    "title": self.clean_text(member.get("title", "")),
                })
        processed["faculty"] = processed_faculty
        
        # Process other fields
        processed["schedules"] = self.clean_text(program.get("schedules", "Not specified"))
        processed["deadlines"] = self.clean_text(program.get("deadlines", "Not specified"))
        processed["language"] = self.clean_text(program.get("language", "Not specified"))
        processed["location"] = self.clean_text(program.get("location", "Not specified"))
        
        # Add metadata
        processed["program_id"] = f"prog_{hash(processed['url']) % 10000:04d}"
        
        return processed

    def process_data(self) -> List[Dict[str, Any]]:
        """
        Process all program data.

        Returns:
            A list of processed program data.
        """
        raw_data = self.load_data()
        processed_data = []
        
        for program in raw_data:
            try:
                processed_program = self.process_program(program)
                processed_data.append(processed_program)
            except Exception as e:
                logger.error(f"Error processing program {program.get('name', 'Unknown')}: {e}")
        
        logger.info(f"Processed {len(processed_data)} programs")
        return processed_data

    def run(self) -> None:
        """Run the data processor."""
        logger.info("Starting data processing...")
        processed_data = self.process_data()
        self.save_data(processed_data)
        logger.info("Data processing completed")

    def generate_stats(self) -> Dict[str, Any]:
        """
        Generate statistics about the processed data.

        Returns:
            A dictionary containing statistics.
        """
        try:
            processed_data = self.load_data()
            if not processed_data:
                return {"error": "No processed data available"}
            
            # Convert to DataFrame for easier analysis
            df = pd.DataFrame(processed_data)
            
            # Basic stats
            stats = {
                "total_programs": len(df),
                "languages": {},
                "locations": {},
                "duration_months": {
                    "min": None,
                    "max": None,
                    "avg": None,
                },
                "costs": {
                    "min": {},
                    "max": {},
                    "avg": {},
                },
            }
            
            # Language stats
            if "language" in df.columns:
                language_counts = df["language"].value_counts().to_dict()
                stats["languages"] = language_counts
            
            # Location stats
            if "location" in df.columns:
                location_counts = df["location"].value_counts().to_dict()
                stats["locations"] = location_counts
            
            # Duration stats
            if "duration" in df.columns:
                # Extract months from duration dictionaries
                months = [d.get("months") for d in df["duration"] if d.get("months") is not None]
                if months:
                    stats["duration_months"]["min"] = min(months)
                    stats["duration_months"]["max"] = max(months)
                    stats["duration_months"]["avg"] = sum(months) / len(months)
            
            # Cost stats by currency
            if "costs" in df.columns:
                # Group costs by currency
                currencies = {}
                for cost in df["costs"]:
                    currency = cost.get("currency")
                    amount = cost.get("amount")
                    if currency and amount is not None:
                        if currency not in currencies:
                            currencies[currency] = []
                        currencies[currency].append(amount)
                
                # Calculate stats for each currency
                for currency, amounts in currencies.items():
                    if amounts:
                        stats["costs"]["min"][currency] = min(amounts)
                        stats["costs"]["max"][currency] = max(amounts)
                        stats["costs"]["avg"][currency] = sum(amounts) / len(amounts)
            
            return stats
        except Exception as e:
            logger.error(f"Error generating stats: {e}")
            return {"error": str(e)}


if __name__ == "__main__":
    processor = DataProcessor()
    processor.run()
    stats = processor.generate_stats()
    print(json.dumps(stats, indent=2))
