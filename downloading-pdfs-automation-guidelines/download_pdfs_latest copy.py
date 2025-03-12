import json
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

from download_functions import (
    download_pdf_file,
    google_search_for_pdf,
    search_ebm_portal,
    search_trip_database,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# File paths - Constants in UPPER_CASE for PEP-8
INPUT_FILE = "final_guidelines_v6.json"
OUTPUT_FILE = "final_guidelines_v7.json"
OUTPUT_FOLDER = "guidelines_database"
CHECKPOINT_FILE = "checkpoint.json"


def load_checkpoint():
    """Load or create checkpoint JSON file."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as checkpoint_file:
            return json.load(checkpoint_file)
    return {"completed": [], "failed": []}


def save_checkpoint(checkpoint_data):
    """Save checkpoint to JSON file."""
    with open(CHECKPOINT_FILE, "w") as checkpoint_file:
        json.dump(checkpoint_data, checkpoint_file, indent=4)


def setup_selenium():
    """Initialize and configure the Selenium WebDriver."""
    options = uc.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = uc.Chrome(options=options)
    return driver


def get_category_and_pdf(title):
    """
    Try EBM Portal first, then Trip Database, and finally Google search for a PDF link.

    Args:
        title (str): The title of the guideline to search for.

    Returns:
        tuple: A tuple containing:
            category (str, optional): Category of the guideline (may be None).
            pdf_link (str, optional): URL of the PDF if found, otherwise None.
    """
    driver = setup_selenium()

    # Step 1: Search EBM Portal
    category = None
    pdf_link = search_ebm_portal(driver, title)

    # Step 2: If no PDF found in EBM Portal, search in Trip Database
    if not pdf_link:
        category, pdf_link = search_trip_database(driver, title)

    # Step 3: If no PDF found in Trip Database, perform Google search
    if not pdf_link:
        pdf_link = google_search_for_pdf(driver, title)

    driver.quit()
    return category, pdf_link


if __name__ == "__main__":
    checkpoint_data = load_checkpoint()

    # Load previous progress if it exists - corrected loading and variable name
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r") as outfile_read:  # More descriptive variable name
            updated_guidelines_data = json.load(outfile_read)
    else:
        with open(INPUT_FILE, "r") as infile_read:    # More descriptive variable name
            updated_guidelines_data = json.load(infile_read)

    progress_bar = tqdm(
        total=len(updated_guidelines_data), desc="Processing Guidelines", unit="item"
    )

    for guideline in updated_guidelines_data:
        title = guideline["title"]
        if title in checkpoint_data["completed"]:
            logging.info(f"Skipping already processed title: {title}")
            progress_bar.update(1)
            continue

        category, pdf_url = get_category_and_pdf(title)  # Corrected function call
        pdf_saved_status = False
        folder_name = os.path.join(OUTPUT_FOLDER, title.replace(" ", "_").replace(":", "").replace("/", "")) # Use os.path.join

        if pdf_url:
            try:
                os.makedirs(folder_name, exist_ok=True)
                save_path = os.path.join(folder_name, f"{title.replace(' ', '_').replace(':', '').replace('/', '')}.pdf") # Use os.path.join and f-string
                pdf_saved_status = download_pdf_file(pdf_url, save_path)
            except Exception as exception_err:  # More descriptive variable name for exception
                logging.error(f"Error saving PDF for {title}: {exception_err}") # Use logging for errors
                pdf_saved_status = False

        # Update JSON data - improved readability
        guideline["pdf_saved"] = pdf_saved_status
        guideline["pdf_link"] = pdf_url if pdf_url else ""  # More concise conditional assignment

        if not pdf_saved_status and os.path.exists(folder_name):
            shutil.rmtree(folder_name)  # Delete empty folder if no PDF was downloaded

        if pdf_saved_status:
            checkpoint_data["completed"].append(title)
        else:
            checkpoint_data["failed"].append(title)

        # Save checkpoint and JSON after each iteration - clearer comments
        save_checkpoint(checkpoint_data)
        with open(OUTPUT_FILE, "w") as outfile_write: # More descriptive variable name
            json.dump(updated_guidelines_data, outfile_write, indent=4)

        progress_bar.update(1)

    print(f"Process Complete! Updated guidelines saved to {OUTPUT_FILE}")