"""
Web scraper for extracting program information from the University of St. Gallen Executive School website.
"""
import json
import logging
import os
import platform
import time
from typing import Dict, List, Optional, Set

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from src.scraper.parser import ProgramParser
from src.utils.logging import get_logger
from config import BASE_URL, RAW_DATA_PATH, SCRAPER_HEADERS, SCRAPER_TIMEOUT

logger = get_logger(__name__)


class Scraper:
    """Scraper for the University of St. Gallen Executive School website."""

    def __init__(self, use_selenium: bool = False):
        """
        Initialize the scraper.

        Args:
            use_selenium: Whether to use Selenium for scraping (for JavaScript-heavy pages).
        """
        self.base_url = BASE_URL
        self.headers = SCRAPER_HEADERS
        self.timeout = SCRAPER_TIMEOUT
        self.use_selenium = use_selenium
        self.driver = None
        self.parser = ProgramParser()
        self.visited_urls: Set[str] = set()

    def _get_chrome_install_instructions(self) -> str:
        """Get Chrome installation instructions based on the operating system."""
        system = platform.system().lower()
        
        if system == "darwin":  # macOS
            return "Install Chrome via: brew install --cask google-chrome"
        elif system == "linux":
            # Check if it's Ubuntu/Debian or other
            try:
                with open("/etc/os-release", "r") as f:
                    os_info = f.read().lower()
                if "ubuntu" in os_info or "debian" in os_info:
                    return "Install Chrome via: sudo apt-get update && sudo apt-get install google-chrome-stable"
                else:
                    return "Install Chrome from your package manager or download from https://www.google.com/chrome/"
            except FileNotFoundError:
                return "Install Chrome from your package manager or download from https://www.google.com/chrome/"
        elif system == "windows":
            return "Download Chrome from https://www.google.com/chrome/"
        else:
            return "Download Chrome from https://www.google.com/chrome/"

    def _setup_selenium(self) -> None:
        """Set up Selenium WebDriver with proper error handling."""
        if self.use_selenium and self.driver is None:
            logger.info("Setting up Selenium WebDriver...")
            
            try:
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--remote-debugging-port=9222")
                
                # Try to install ChromeDriver
                try:
                    service = Service(ChromeDriverManager("140.0.7339").install())
                except Exception as e:
                    logger.error(f"Failed to install ChromeDriver: {e}")
                    raise WebDriverException("ChromeDriver installation failed")
                
                # Try to create Chrome WebDriver
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("Chrome WebDriver initialized successfully")
                
            except WebDriverException as e:
                error_msg = str(e)
                if "chrome binary" in error_msg.lower() or "chromedriver" in error_msg.lower():
                    install_instructions = self._get_chrome_install_instructions()
                    logger.error(
                        f"Chrome browser not found. Please install Chrome first.\n"
                        f"Installation instructions for your system:\n{install_instructions}\n"
                        f"After installation, restart the application."
                    )
                    raise WebDriverException(
                        f"Chrome browser not found. {install_instructions}"
                    )
                else:
                    logger.error(f"WebDriver setup failed: {e}")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error during WebDriver setup: {e}")
                raise WebDriverException(f"WebDriver setup failed: {e}")

    def _cleanup_selenium(self) -> None:
        """Clean up Selenium WebDriver."""
        if self.driver is not None:
            logger.info("Cleaning up Selenium WebDriver...")
            self.driver.quit()
            self.driver = None

    def _get_page_content(self, url: str) -> Optional[str]:
        """
        Get the HTML content of a page.

        Args:
            url: The URL to fetch.

        Returns:
            The HTML content of the page, or None if the request failed.
        """
        try:
            if self.use_selenium:
                self._setup_selenium()
                self.driver.get(url)
                # Wait for JavaScript to load
                time.sleep(2)
                return self.driver.page_source
            else:
                response = requests.get(url, headers=self.headers, timeout=self.timeout)
                response.raise_for_status()
                return response.text
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def _extract_program_links(self, html_content: str) -> List[str]:
        """
        Extract links to program pages from the main page.

        Args:
            html_content: The HTML content of the main page.

        Returns:
            A list of URLs to program pages.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        program_links = []

        # Try multiple selectors in order of specificity
        selectors = [
            "a.program-link",  # Specific program link class
            "a[href*='program']",  # Links containing 'program' in href
            "a[href*='emba']",  # Links containing 'emba' in href
            ".program a",  # Links inside program containers
            ".course a",  # Links inside course containers
            "a"  # Fallback to all links
        ]
        
        for selector in selectors:
            link_elements = soup.select(selector)
            if link_elements:
                logger.info(f"Using selector: {selector} (found {len(link_elements)} links)")
                break
        else:
            logger.warning("No links found with any selector")
            return []
        
        for link in link_elements:
            href = link.get("href")
            if href:
                # Filter out anchor-only links (starting with #)
                if href.startswith("#"):
                    continue
                
                # Filter out mailto, tel, and javascript links
                if href.startswith(("mailto:", "tel:", "javascript:")):
                    continue
                
                # Filter out external links that don't belong to the target domain
                if href.startswith("http") and "unisg.ch" not in href:
                    continue
                
                # Make sure we have absolute URLs
                if href.startswith("/"):
                    href = f"https://emba.unisg.ch{href}"
                elif not href.startswith("http"):
                    # Relative URL
                    href = f"https://emba.unisg.ch/{href.lstrip('/')}"
                
                # Avoid duplicates
                if href not in program_links:
                    program_links.append(href)

        logger.info(f"Found {len(program_links)} valid program links after filtering")
        return program_links

    def scrape_main_page(self) -> List[str]:
        """
        Scrape the main page to find links to program pages.

        Returns:
            A list of URLs to program pages.
        """
        logger.info(f"Scraping main page: {self.base_url}")
        html_content = self._get_page_content(self.base_url)
        
        if not html_content:
            logger.error("Failed to fetch main page")
            return []
        
        return self._extract_program_links(html_content)

    def scrape_program_page(self, url: str) -> Optional[Dict]:
        """
        Scrape a program page to extract program information.

        Args:
            url: The URL of the program page.

        Returns:
            A dictionary containing program information, or None if scraping failed.
        """
        if url in self.visited_urls:
            logger.info(f"Already visited {url}, skipping")
            return None
        
        logger.info(f"Scraping program page: {url}")
        self.visited_urls.add(url)
        
        html_content = self._get_page_content(url)
        if not html_content:
            logger.error(f"Failed to fetch program page: {url}")
            return None
        
        program_data = self.parser.parse_program_page(html_content, url)
        return program_data

    def scrape_all_programs(self) -> List[Dict]:
        """
        Scrape all program pages.

        Returns:
            A list of dictionaries containing program information.
        """
        try:
            program_links = self.scrape_main_page()
            programs_data = []
            
            for link in program_links:
                program_data = self.scrape_program_page(link)
                if program_data:
                    programs_data.append(program_data)
                # Be nice to the server
                time.sleep(1)
            
            return programs_data
        finally:
            self._cleanup_selenium()

    def save_data(self, data: List[Dict], output_path: str = RAW_DATA_PATH) -> None:
        """
        Save scraped data to a JSON file.

        Args:
            data: The data to save.
            output_path: The path to save the data to.
        """
        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(data)} programs to {output_path}")

    def run(self) -> None:
        """Run the scraper and save the results."""
        logger.info("Starting scraper...")
        programs_data = self.scrape_all_programs()
        self.save_data(programs_data)
        logger.info("Scraping completed")


if __name__ == "__main__":
    scraper = Scraper(use_selenium=True)
    scraper.run()
