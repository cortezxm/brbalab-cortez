import ssl
import urllib.request
from datetime import datetime
import pandas as pd
import bs4 as bs
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time


def extract_fifa_countries():
    """
    Extract all FIFA countries from the ranking page.
    Returns list of country names in 11v11.com format (e.g., 'argentina', 'spain', etc.)
    """
    
    from selenium.webdriver.chrome.options import Options
    
    chrome_options = Options()
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    countries = []
    
    with Chrome(options=chrome_options) as driver:
        driver.set_page_load_timeout(30)
        
        try:
            # Handle privacy popup
            driver.get('https://www.11v11.com/')
            try:
                agree_span = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'AGREE')]"))
                )
                agree_span.click()
                time.sleep(1)
            except TimeoutException:
                pass
            
            # Navigate to FIFA ranking page
            ranking_url = 'https://www.11v11.com/teams/germany/option/ranking/fullranking/true/'
            print(f"Navigating to: {ranking_url}")
            
            driver.get(ranking_url)
            time.sleep(3)  # Give page time to load
            
            # Get page source and parse using BeautifulSoup
            page_source = driver.page_source
            soup = bs.BeautifulSoup(page_source, features="lxml")
            
            # Find the ranking table
            ranking_table = soup.find('table', class_='ranking')
            if not ranking_table:
                print("ERROR: No ranking table found")
                return []
                       
            # Find all rows in tbody
            tbody = ranking_table.find('tbody')
            if not tbody:
                print("ERROR: No tbody found in ranking table")
                return []
            
            rows = tbody.find_all('tr')
            print(f"Found {len(rows)} countries in ranking")
            
            # Extract country names from each row
            for i, row in enumerate(rows):
                try:
                    # Find the link to the country page
                    country_link = row.find('a')
                    if country_link:
                        href = country_link.get('href')
                        country_name = country_link.get_text(strip=True)
                        
                        if href and href.startswith('/teams/'):
                            # Extract country identifier from URL: /teams/argentina -> argentina
                            country_id = href.replace('/teams/', '').strip('/')
                            countries.append({
                                'position': i + 1,
                                'country_name': country_name,
                                'country_id': country_id,
                                'url': f"https://www.11v11.com{href}"
                            })
                            
                            # Show progress every 25 countries
                            if (i + 1) % 25 == 0:
                                print(f"  Processed {i + 1} countries...")
                        
                except Exception as e:
                    print(f"Error processing row {i + 1}: {str(e)}")
                    continue
            
            print(f"Successfully extracted {len(countries)} countries")
            return countries
            
        except Exception as e:
            print(f"ERROR during extraction: {str(e)}")
            return []


def save_countries_data(countries):
    """
    Save countries data to multiple formats for easy use.
    """
    if not countries:
        print("No countries to save")
        return
    
    # Create DataFrame
    df = pd.DataFrame(countries)
    
    # Save full data to CSV
    full_csv = 'fifa_countries.csv'
    df.to_csv(full_csv, index=False)
    
    # Save just country IDs to simple text file (for easy iteration)
    country_ids = [country['country_id'] for country in countries]
    
    # Save as Python list format
    list_file = 'fifa_countries_list.py'
    with open(list_file, 'w', encoding='utf-8') as f:
        f.write("# FIFA Countries List for 11v11.com scraping\n")
        f.write("# Auto-generated on " + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "\n\n")
        f.write("FIFA_COUNTRIES = [\n")
        for country_id in country_ids:
            f.write(f"    '{country_id}',\n")
        f.write("]\n\n")
        f.write(f"# Total countries: {len(country_ids)}\n")
        f.write("# Usage: from fifa_countries_list import FIFA_COUNTRIES\n")
        
    # Save as simple text file
    txt_file = 'fifa_countries.txt'
    with open(txt_file, 'w', encoding='utf-8') as f:
        for country_id in country_ids:
            f.write(country_id + '\n')


def test_countries_extraction():
    """
    Main function to extract and save FIFA countries.
    """
    # Extract countries
    countries = extract_fifa_countries()
    
    if countries:
        # Save data in multiple formats
        save_countries_data(countries)


if __name__ == "__main__":
    test_countries_extraction()