import logging
import os
import shutil  # For deleting empty folders
import time

import requests
import undetected_chromedriver as uc
import wget
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tqdm import tqdm


def extract_pmc_pdf(driver, pmc_url):
    """
    Extract and return the PDF link from a PubMed Central (PMC) page.

    Args:
        driver: Selenium WebDriver instance.
        pmc_url (str): URL of the PubMed Central page.

    Returns:
        str: PDF URL if found, otherwise None.
    """
    driver.get(pmc_url)
    time.sleep(5)

    try:
        pdf_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href$='.pdf']"))
        )
        pdf_url = pdf_element.get_attribute("href")
        if pdf_url.startswith("/pdf"):
            pdf_url = pmc_url.split("/PMC")[0] + pdf_url
        logging.info(f"Found PDF on PMC: {pdf_url}")
        return pdf_url
    except Exception as exception_err:  # More descriptive variable name
        logging.error(f"Failed to extract PDF from PMC: {exception_err}")
        return None


def extract_pdf_from_webpage(driver, webpage_url):
    """
    Visit a webpage and attempt to find a downloadable PDF link.

    Args:
        driver: Selenium WebDriver instance.
        webpage_url (str): URL of the webpage to check.

    Returns:
        str: PDF URL if found, otherwise None.
    """
    driver.get(webpage_url)
    time.sleep(5)

    try:
        pdf_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href$='.pdf']"))
        )
        pdf_url = pdf_element.get_attribute("href")
        if pdf_url.startswith("/"):
            pdf_url = webpage_url.rstrip("/") + pdf_url
        logging.info(f"Found PDF on webpage: {pdf_url}")
        return pdf_url
    except Exception as exception_err:  # More descriptive variable name
        logging.error(f"No PDF link found on webpage: {exception_err}")
        return None


def search_trip_database(driver, expected_title):
    """
    Search Trip Database for a given title, verify it, and extract category and first PDF URL.

    Args:
        driver: Selenium WebDriver instance.
        expected_title (str): The expected title of the guideline.

    Returns:
        tuple: A tuple containing:
            category_label (str, optional): Category label from Trip Database, None if not found.
            pdf_link (str, optional): PDF URL if found, otherwise None.
    """
    formatted_title = expected_title.replace(" ", "%20")
    search_url = f"https://www.tripdatabase.com/Searchresult?criteria={formatted_title}&search_type=standard"
    driver.get(search_url)
    time.sleep(5)

    try:
        first_result = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".result"))
        )
        actual_title = first_result.find_element(By.CSS_SELECTOR, "a h5").text.strip()
        logging.info(f"Found Title in Trip Database: {actual_title}")

        if actual_title.lower() != expected_title.lower():
            logging.warning(
                f"Title mismatch in Trip Database. Expected: '{expected_title}', Found: '{actual_title}'"
            )
            return None, None

        category_label = first_result.find_element(
            By.CSS_SELECTOR, ".result--taxonomies .badge-evidence-secondary"
        ).text.strip()
        pdf_element = first_result.find_elements(By.CSS_SELECTOR, "a[href$='.pdf']")
        pdf_link = pdf_element[0].get_attribute("href") if pdf_element else None

        return category_label, pdf_link
    except Exception as exception_err:  # More descriptive variable name
        logging.error(f"Error extracting from Trip Database: {exception_err}")
        return None, None


def google_search_for_pdf(driver, title):
    """
    Perform a Google search to find the first valid PDF, PMC, or webpage.

    Args:
        driver: Selenium WebDriver instance.
        title (str): The title of the guideline to search for.

    Returns:
        str: URL of the PDF, PMC, or webpage if found, otherwise None.
    """
    search_query = f"{title} full text pdf"
    google_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
    driver.get(google_url)
    time.sleep(5)

    try:
        search_results = driver.find_elements(By.CSS_SELECTOR, "div.tF2Cxc a")[:3]
        links = list(
            set(result.get_attribute("href").split("#")[0] for result in search_results)
        )

        pmc_url = None
        webpage_url = None

        for url in links:
            if "login" in url.lower():
                logging.warning(f"Skipping login-required link from Google search: {url}")
                continue

            if url.lower().endswith(".pdf"):
                logging.info(f"Found PDF on Google: {url}")
                return url

            if "pmc.ncbi.nlm.nih.gov" in url:
                pmc_url = url

            if webpage_url is None:
                webpage_url = url

        if pmc_url:
            logging.info(f"No direct PDF found in Google, but found PMC: {pmc_url}")
            return extract_pmc_pdf(driver, pmc_url)

        if webpage_url:
            if "login" in webpage_url.lower():
                return None
            logging.info(
                f"No direct PDF or PMC found in Google, extracting from webpage: {webpage_url}"
            )
            return extract_pdf_from_webpage(driver, webpage_url)

        logging.warning("No direct PDF, PMC, or valid webpage found in Google search results.")
        return None

    except Exception as exception_err:  # More descriptive variable name
        logging.error(f"Google search error: {exception_err}")
        return None


def download_pdf_file(pdf_url, save_path):
    """
    Download the PDF file from a given URL using wget, with fallback to requests.

    Args:
        pdf_url (str): URL of the PDF file.
        save_path (str): Path to save the downloaded PDF.

    Returns:
        bool: True if download successful, False otherwise.
    """
    try:
        wget.download(pdf_url, out=save_path)
        logging.info(f"Successfully downloaded PDF using wget: {save_path}")
        return True
    except Exception as wget_error:  # More descriptive variable name
        logging.error(f"wget download failed: {wget_error}")
        logging.info("Falling back to requests for PDF download...")
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
            }
            response = requests.get(pdf_url, headers=headers, stream=True, timeout=30) # Increased timeout
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            with open(save_path, "wb") as pdf_file:
                for chunk in response.iter_content(chunk_size=8192):
                    pdf_file.write(chunk)

            logging.info(f"Successfully downloaded PDF using requests: {save_path}")
            return True

        except requests.exceptions.HTTPError as http_err:
            logging.error(f"Requests HTTP Error: {http_err}")
            logging.error(f"PDF download failed using requests: HTTP Error - {http_err}")
            return False
        except requests.exceptions.RequestException as req_err:
            logging.error(f"Requests error: {req_err}")
            logging.error(f"PDF download failed using requests: Request Exception - {req_err}")
            return False
        except Exception as exception_err:  # More descriptive variable name
            logging.error(f"Unexpected error during requests download: {exception_err}")
            logging.error(
                f"PDF download failed using requests: Unexpected Error - {exception_err}"
            )
            return False


def search_ebm_portal(driver, title):
    """
    Search for a guideline on EBM Portal and extract the PDF link.

    Args:
        driver: Selenium WebDriver instance.
        title (str): The title of the guideline to search for.

    Returns:
        str: PDF URL if found, otherwise None.
    """
    search_url = f"https://guidelines.ebmportal.com/?q={title.replace(' ', '+')}"
    driver.get(search_url)
    time.sleep(5)

    try:
        # Click on the first search result
        first_result = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.node"))
        )

        # Click on the first result to open the guideline page
        first_result.click()
        time.sleep(5)

        # Locate the PDF download link
        pdf_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "a.btn.btn-default.button[href$='.pdf']",
                )
            )
        )

        pdf_url = pdf_element.get_attribute("href")
        logging.info(f"Found PDF on EBM Portal: {pdf_url}")
        return pdf_url

    except Exception as exception_err:  # More descriptive variable name
        logging.error(f"Error extracting from EBM Portal: {exception_err}")
        return None