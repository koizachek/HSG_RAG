"""
Parser for extracting structured information from program pages.
"""
import logging
import re
from typing import Dict, List, Optional, Any

from bs4 import BeautifulSoup
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ProgramParser:
    """Parser for extracting program information from HTML content."""

    def parse_program_page(self, html_content: str, url: str) -> Dict[str, Any]:
        """
        Parse a program page to extract structured information.

        Args:
            html_content: The HTML content of the program page.
            url: The URL of the program page.

        Returns:
            A dictionary containing structured program information.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Initialize program data with URL
        program_data = {
            "url": url,
            "name": self._extract_program_name(soup),
            "duration": self._extract_duration(soup),
            "curriculum": self._extract_curriculum(soup),
            "costs": self._extract_costs(soup),
            "admission_requirements": self._extract_admission_requirements(soup),
            "schedules": self._extract_schedules(soup),
            "faculty": self._extract_faculty(soup),
            "deadlines": self._extract_deadlines(soup),
            "language": self._extract_language(soup),
            "location": self._extract_location(soup),
            "description": self._extract_description(soup),
        }
        
        return program_data

    def _extract_program_name(self, soup: BeautifulSoup) -> str:
        """Extract the program name from the soup."""
        # This is a placeholder. Update with actual selectors based on website structure.
        try:
            # Try to find the program name in the page title or a heading
            title_element = soup.find("h1") or soup.find("title")
            if title_element:
                return title_element.get_text().strip()
        except Exception as e:
            logger.error(f"Error extracting program name: {e}")
        
        return "Unknown Program"

    def _extract_duration(self, soup: BeautifulSoup) -> str:
        """Extract the program duration from the soup."""
        try:
            # Look for duration information
            # This is a placeholder. Update with actual selectors.
            duration_section = soup.find("div", class_="program-duration")
            if duration_section:
                return duration_section.get_text().strip()
            
            # Try to find duration in the text
            text = soup.get_text()
            duration_patterns = [
                r"Duration:?\s*([^\.]+)",
                r"Program length:?\s*([^\.]+)",
                r"(\d+)\s+months",
                r"(\d+)\s+years",
            ]
            
            for pattern in duration_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        except Exception as e:
            logger.error(f"Error extracting duration: {e}")
        
        return "Not specified"

    def _extract_curriculum(self, soup: BeautifulSoup) -> List[str]:
        """Extract the curriculum information from the soup."""
        curriculum = []
        try:
            # Look for curriculum information
            # This is a placeholder. Update with actual selectors.
            curriculum_section = soup.find("div", class_="program-curriculum")
            if curriculum_section:
                # Look for list items
                items = curriculum_section.find_all("li")
                if items:
                    for item in items:
                        curriculum.append(item.get_text().strip())
                else:
                    # If no list items, get the text
                    curriculum.append(curriculum_section.get_text().strip())
        except Exception as e:
            logger.error(f"Error extracting curriculum: {e}")
        
        return curriculum

    def _extract_costs(self, soup: BeautifulSoup) -> str:
        """Extract the program costs from the soup."""
        try:
            # Look for cost information
            # This is a placeholder. Update with actual selectors.
            cost_section = soup.find("div", class_="program-costs")
            if cost_section:
                return cost_section.get_text().strip()
            
            # Try to find cost in the text
            text = soup.get_text()
            cost_patterns = [
                r"Cost:?\s*([^\.]+)",
                r"Tuition:?\s*([^\.]+)",
                r"Fee:?\s*([^\.]+)",
                r"CHF\s*[\d\',]+",
                r"€\s*[\d\',]+",
            ]
            
            for pattern in cost_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(0).strip()
        except Exception as e:
            logger.error(f"Error extracting costs: {e}")
        
        return "Not specified"

    def _extract_admission_requirements(self, soup: BeautifulSoup) -> List[str]:
        """Extract the admission requirements from the soup."""
        requirements = []
        try:
            # Look for admission requirements
            # This is a placeholder. Update with actual selectors.
            requirements_section = soup.find("div", class_="program-requirements")
            if requirements_section:
                # Look for list items
                items = requirements_section.find_all("li")
                if items:
                    for item in items:
                        requirements.append(item.get_text().strip())
                else:
                    # If no list items, get the text
                    requirements.append(requirements_section.get_text().strip())
        except Exception as e:
            logger.error(f"Error extracting admission requirements: {e}")
        
        return requirements

    def _extract_schedules(self, soup: BeautifulSoup) -> str:
        """Extract the program schedules from the soup."""
        try:
            # Look for schedule information
            # This is a placeholder. Update with actual selectors.
            schedule_section = soup.find("div", class_="program-schedule")
            if schedule_section:
                return schedule_section.get_text().strip()
            
            # Try to find schedule in the text
            text = soup.get_text()
            schedule_patterns = [
                r"Schedule:?\s*([^\.]+)",
                r"Classes:?\s*([^\.]+)",
                r"Start date:?\s*([^\.]+)",
            ]
            
            for pattern in schedule_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        except Exception as e:
            logger.error(f"Error extracting schedules: {e}")
        
        return "Not specified"

    def _extract_faculty(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract the faculty information from the soup."""
        faculty = []
        try:
            # Look for faculty information
            # This is a placeholder. Update with actual selectors.
            faculty_section = soup.find("div", class_="program-faculty")
            if faculty_section:
                faculty_members = faculty_section.find_all("div", class_="faculty-member")
                for member in faculty_members:
                    name_element = member.find("h3") or member.find("strong")
                    name = name_element.get_text().strip() if name_element else "Unknown"
                    
                    title_element = member.find("p", class_="faculty-title")
                    title = title_element.get_text().strip() if title_element else ""
                    
                    faculty.append({
                        "name": name,
                        "title": title,
                    })
        except Exception as e:
            logger.error(f"Error extracting faculty: {e}")
        
        return faculty

    def _extract_deadlines(self, soup: BeautifulSoup) -> str:
        """Extract the application deadlines from the soup."""
        try:
            # Look for deadline information
            # This is a placeholder. Update with actual selectors.
            deadline_section = soup.find("div", class_="program-deadlines")
            if deadline_section:
                return deadline_section.get_text().strip()
            
            # Try to find deadlines in the text
            text = soup.get_text()
            deadline_patterns = [
                r"Deadline:?\s*([^\.]+)",
                r"Application deadline:?\s*([^\.]+)",
                r"Apply by:?\s*([^\.]+)",
            ]
            
            for pattern in deadline_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        except Exception as e:
            logger.error(f"Error extracting deadlines: {e}")
        
        return "Not specified"

    def _extract_language(self, soup: BeautifulSoup) -> str:
        """Extract the program language from the soup."""
        try:
            # Look for language information
            # This is a placeholder. Update with actual selectors.
            language_section = soup.find("div", class_="program-language")
            if language_section:
                return language_section.get_text().strip()
            
            # Try to find language in the text
            text = soup.get_text()
            language_patterns = [
                r"Language:?\s*([^\.]+)",
                r"Taught in:?\s*([^\.]+)",
            ]
            
            for pattern in language_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        except Exception as e:
            logger.error(f"Error extracting language: {e}")
        
        return "Not specified"

    def _extract_location(self, soup: BeautifulSoup) -> str:
        """Extract the program location from the soup."""
        try:
            # Look for location information
            # This is a placeholder. Update with actual selectors.
            location_section = soup.find("div", class_="program-location")
            if location_section:
                return location_section.get_text().strip()
            
            # Try to find location in the text
            text = soup.get_text()
            location_patterns = [
                r"Location:?\s*([^\.]+)",
                r"Campus:?\s*([^\.]+)",
                r"Venue:?\s*([^\.]+)",
            ]
            
            for pattern in location_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        except Exception as e:
            logger.error(f"Error extracting location: {e}")
        
        return "Not specified"

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract the program description from the soup."""
        try:
            # Look for description information
            # This is a placeholder. Update with actual selectors.
            description_section = soup.find("div", class_="program-description")
            if description_section:
                return description_section.get_text().strip()
            
            # Try to find a general description
            paragraphs = soup.find_all("p")
            if paragraphs:
                # Get the first few paragraphs as the description
                description = " ".join([p.get_text().strip() for p in paragraphs[:3]])
                return description
        except Exception as e:
            logger.error(f"Error extracting description: {e}")
        
        return "No description available"
