import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import time
import random
from typing import List, Dict, Optional

class PreciseQCWaterScraper:
    """
    Updated scraper based on actual website structure from screenshots
    """
    
    def __init__(self):
        self.maynilad_url = 'https://www.mayniladwater.com.ph/service-advisories-2/'
        self.manila_water_url = 'https://www.manilawater.com/customers/service-advisories'
        
        # Enhanced session with better headers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        })

    def scrape_maynilad_tables(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extract data from Maynilad's specific table structure
        Based on the screenshots showing two tables with QC data
        """
        interruptions = []
        
        try:
            # Look for tables containing interruption data
            tables = soup.find_all('table')
            
            for table_idx, table in enumerate(tables):
                st.info(f"Processing Maynilad table {table_idx + 1}...")
                
                # Find table headers to understand structure
                headers = []
                header_row = table.find('tr')
                if header_row:
                    headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
                
                # Look for rows with QC data
                rows = table.find_all('tr')[1:]  # Skip header row
                
                for row in rows:
                    cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                    
                    if len(cells) < 3:  # Skip rows with insufficient data
                        continue
                    
                    # Check if this row contains Quezon City data
                    row_text = ' '.join(cells).lower()
                    
                    if 'quezon city' in row_text or 'qc' in row_text:
                        # Extract data based on expected structure
                        # From screenshots: City, Barangay, Specific Area, From, To, Time, Reason
                        
                        interruption_data = {
                            'provider': 'Maynilad',
                            'source': 'Service Advisories Table',
                            'raw_data': cells,
                            'scraped_at': datetime.now()
                        }
                        
                        # Try to map cells to expected columns
                        if len(cells) >= 6:
                            interruption_data.update({
                                'city': cells[0] if len(cells) > 0 else '',
                                'barangay': cells[1] if len(cells) > 1 else '',
                                'specific_area': cells[2] if len(cells) > 2 else '',
                                'date_from': cells[3] if len(cells) > 3 else '',
                                'date_to': cells[4] if len(cells) > 4 else '',
                                'time': cells[5] if len(cells) > 5 else '',
                                'reason': cells[6] if len(cells) > 6 else ''
                            })
                            
                            # Create description
                            description = f"Maynilad service interruption in {interruption_data['barangay']}, {interruption_data['specific_area']}. "
                            description += f"Schedule: {interruption_data['date_from']} to {interruption_data['date_to']}, {interruption_data['time']}. "
                            description += f"Reason: {interruption_data['reason']}"
                            
                            interruption_data['description'] = description
                            interruption_data['areas'] = [interruption_data['barangay']]
                        
                        else:
                            # Fallback for different table structures
                            interruption_data['description'] = f"Quezon City water service interruption: {' | '.join(cells)}"
                            interruption_data['areas'] = ['Quezon City']
                        
                        interruptions.append(interruption_data)
            
            st.success(f"Found {len(interruptions)} Maynilad QC interruptions")
            
        except Exception as e:
            st.error(f"Error parsing Maynilad tables: {str(e)}")
        
        return interruptions

    def scrape_manila_water_table(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extract data from Manila Water's table structure
        Based on screenshot showing: Start, End, Affected City/Municipality, Location, Activity, Affected Areas
        """
        interruptions = []
        
        try:
            # Look for the main data table
            tables = soup.find_all('table')
            
            for table_idx, table in enumerate(tables):
                st.info(f"Processing Manila Water table {table_idx + 1}...")
                
                # Find headers
                headers = []
                header_row = table.find('tr')
                if header_row:
                    headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
                
                # Process data rows
                rows = table.find_all('tr')[1:]  # Skip header
                
                for row in rows:
                    cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                    
                    if len(cells) < 3:
                        continue
                    
                    # Check if this affects Quezon City
                    row_text = ' '.join(cells).lower()
                    
                    # Look for QC indicators
                    qc_indicators = ['quezon city', 'qc', 'diliman', 'fairview', 'novaliches', 'commonwealth']
                    
                    if any(indicator in row_text for indicator in qc_indicators):
                        interruption_data = {
                            'provider': 'Manila Water',
                            'source': 'Service Advisories Table',
                            'raw_data': cells,
                            'scraped_at': datetime.now()
                        }
                        
                        # Map to expected Manila Water structure
                        if len(cells) >= 6:
                            interruption_data.update({
                                'start_date': cells[0] if len(cells) > 0 else '',
                                'end_date': cells[1] if len(cells) > 1 else '',
                                'affected_city': cells[2] if len(cells) > 2 else '',
                                'location': cells[3] if len(cells) > 3 else '',
                                'activity': cells[4] if len(cells) > 4 else '',
                                'affected_areas': cells[5] if len(cells) > 5 else ''
                            })
                            
                            # Create description
                            description = f"Manila Water {interruption_data['activity']} in {interruption_data['affected_city']}. "
                            description += f"Location: {interruption_data['location']}. "
                            description += f"Schedule: {interruption_data['start_date']} to {interruption_data['end_date']}. "
                            description += f"Affected areas: {interruption_data['affected_areas']}"
                            
                            interruption_data['description'] = description
                            interruption_data['areas'] = [interruption_data['affected_areas']]
                        
                        else:
                            interruption_data['description'] = f"Manila Water service advisory: {' | '.join(cells)}"
                            interruption_data['areas'] = ['Quezon City']
                        
                        interruptions.append(interruption_data)
            
            st.success(f"Found {len(interruptions)} Manila Water QC interruptions")
            
        except Exception as e:
            st.error(f"Error parsing Manila Water tables: {str(e)}")
        
        return interruptions

    def scrape_with_robust_retry(self, url: str) -> Optional[BeautifulSoup]:
        """
        Enhanced scraping with multiple retry strategies
        """
        strategies = [
            # Strategy 1: Standard request
            {
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                },
                'timeout': 15
            },
            # Strategy 2: Different user agent
            {
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15'
                },
                'timeout': 20
            },
            # Strategy 3: Mobile user agent
            {
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
                },
                'timeout': 25
            }
        ]
        
        for strategy_idx, strategy in enumerate(strategies):
            try:
                st.info(f"Trying access strategy {strategy_idx + 1} for {url}")
                
                # Wait between attempts
                if strategy_idx > 0:
                    time.sleep(random.uniform(3, 7))
                
                session = requests.Session()
                session.headers.update(strategy['headers'])
                
                response = session.get(url, timeout=strategy['timeout'])
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Validate we got meaningful content
                text_content = soup.get_text(strip=True)
                
                if len(text_content) > 500:  # Reasonable content threshold
                    st.success(f"Successfully accessed {url} with strategy {strategy_idx + 1}")
                    return soup
                else:
                    st.warning(f"Strategy {strategy_idx + 1} got minimal content")
                    
            except Exception as e:
                st.warning(f"Strategy {strategy_idx + 1} failed: {str(e)}")
                continue
        
        st.error(f"All strategies failed for {url}")
        return None

    def get_all_qc_interruptions(self) -> List[Dict]:
        """
        Get all QC water interruptions from both providers
        """
        all_interruptions = []
        
        # Scrape Maynilad
        st.subheader("🔍 Checking Maynilad Service Advisories")
        maynilad_soup = self.scrape_with_robust_retry(self.maynilad_url)
        
        if maynilad_soup:
            maynilad_interruptions = self.scrape_maynilad_tables(maynilad_soup)
            all_interruptions.extend(maynilad_interruptions)
        
        # Wait between requests
        time.sleep(random.uniform(3, 6))
        
        # Scrape Manila Water
        st.subheader("🔍 Checking Manila Water Service Advisories")
        manila_water_soup = self.scrape_with_robust_retry(self.manila_water_url)
        
        if manila_water_soup:
            manila_water_interruptions = self.scrape_manila_water_table(manila_water_soup)
            all_interruptions.extend(manila_water_interruptions)
        
        return all_interruptions

# Cached function for Streamlit
@st.cache_data(ttl=1800)  # Cache for 30 minutes
def get_precise_qc_water_interruptions():
    """Get QC water interruptions with precise table parsing"""
    scraper = PreciseQCWaterScraper()
    return scraper.get_all_qc_interruptions()

def display_precise_water_monitoring():
    """
    Display water monitoring with enhanced data presentation
    """
    st.subheader("💧 QC Water Service Interruptions - Live Data")
    
    # Control buttons
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.write("Real-time monitoring of Maynilad and Manila Water service advisories")
    
    with col2:
        if st.button("🔄 Check Now", key="precise_check"):
            st.cache_data.clear()
    
    with col3:
        show_raw = st.checkbox("Show Raw Data", key="show_raw")
    
    # Get interruptions
    with st.spinner("Accessing water provider websites..."):
        try:
            interruptions = get_precise_qc_water_interruptions()
        except Exception as e:
            st.error(f"Error accessing water services: {e}")
            interruptions = []
    
    # Display results
    if interruptions:
        st.warning(f"⚠️ {len(interruptions)} water service advisories affecting QC")
        
        # Group by provider
        maynilad_interruptions = [i for i in interruptions if i['provider'] == 'Maynilad']
        manila_water_interruptions = [i for i in interruptions if i['provider'] == 'Manila Water']
        
        # Display Maynilad interruptions
        if maynilad_interruptions:
            st.markdown("### 🔵 Maynilad Water Services")
            for interruption in maynilad_interruptions:
                with st.expander(f"Maynilad - {', '.join(interruption.get('areas', ['QC']))}"):
                    st.write(f"**Description:** {interruption.get('description', 'No description available')}")
                    
                    # Show structured data if available
                    if 'barangay' in interruption:
                        st.write(f"**Barangay:** {interruption.get('barangay', 'N/A')}")
                        st.write(f"**Specific Area:** {interruption.get('specific_area', 'N/A')}")
                        st.write(f"**Schedule:** {interruption.get('date_from', 'N/A')} to {interruption.get('date_to', 'N/A')}")
                        st.write(f"**Time:** {interruption.get('time', 'N/A')}")
                        st.write(f"**Reason:** {interruption.get('reason', 'N/A')}")
                    
                    if show_raw:
                        st.json(interruption.get('raw_data', []))
                    
                    st.write(f"**Last Updated:** {interruption['scraped_at'].strftime('%Y-%m-%d %H:%M')}")
        
        # Display Manila Water interruptions
        if manila_water_interruptions:
            st.markdown("### 🔴 Manila Water Company")
            for interruption in manila_water_interruptions:
                with st.expander(f"Manila Water - {', '.join(interruption.get('areas', ['QC']))}"):
                    st.write(f"**Description:** {interruption.get('description', 'No description available')}")
                    
                    # Show structured data if available
                    if 'start_date' in interruption:
                        st.write(f"**Schedule:** {interruption.get('start_date', 'N/A')} to {interruption.get('end_date', 'N/A')}")
                        st.write(f"**Location:** {interruption.get('location', 'N/A')}")
                        st.write(f"**Activity:** {interruption.get('activity', 'N/A')}")
                        st.write(f"**Affected Areas:** {interruption.get('affected_areas', 'N/A')}")
                    
                    if show_raw:
                        st.json(interruption.get('raw_data', []))
                    
                    st.write(f"**Last Updated:** {interruption['scraped_at'].strftime('%Y-%m-%d %H:%M')}")
    
    else:
        st.success("✅ No current water service interruptions reported for QC")
        st.info("💡 If you're experiencing water issues, please contact your water provider directly:")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Manila Water:** 1627")
        with col2:
            st.write("**Maynilad:** 1626")

# Test function specific to the table structures
def test_table_parsing():
    """
    Test function to validate table parsing logic
    """
    st.subheader("🧪 Test Table Parsing")
    
    if st.button("Test Table Structure Detection"):
        scraper = PreciseQCWaterScraper()
        
        with st.spinner("Testing website structure..."):
            # Test Maynilad
            st.write("**Testing Maynilad structure:**")
            maynilad_soup = scraper.scrape_with_robust_retry(scraper.maynilad_url)
            
            if maynilad_soup:
                tables = maynilad_soup.find_all('table')
                st.success(f"Found {len(tables)} tables on Maynilad page")
                
                for i, table in enumerate(tables):
                    rows = len(table.find_all('tr'))
                    st.write(f"Table {i+1}: {rows} rows")
            
            # Test Manila Water
            st.write("**Testing Manila Water structure:**")
            manila_water_soup = scraper.scrape_with_robust_retry(scraper.manila_water_url)
            
            if manila_water_soup:
                tables = manila_water_soup.find_all('table')
                st.success(f"Found {len(tables)} tables on Manila Water page")
                
                for i, table in enumerate(tables):
                    rows = len(table.find_all('tr'))
                    st.write(f"Table {i+1}: {rows} rows")

if __name__ == "__main__":
    st.title("Precise QC Water Interruption Monitor")
    
    # Add testing interface
    with st.expander("🧪 Development Tools"):
        test_table_parsing()
    
    # Main monitoring interface
    display_precise_water_monitoring()
