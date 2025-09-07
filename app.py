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
    def __init__(self):
        self.maynilad_url = 'https://www.mayniladwater.com.ph/service-advisories-2/'
        self.manila_water_url = 'https://www.manilawater.com/customers/service-advisories'

        # Keep ONE session; do NOT advertise 'br' unless you can decode it.
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Referer': 'https://www.google.com/'
        })

    def _decode_html(self, resp: requests.Response) -> str:
        # Handle Brotli if server still sends it
        enc = resp.headers.get('Content-Encoding', '').lower()
        if 'br' in enc:
            try:
                import brotli  # pip install brotli or brotlicffi
                return brotli.decompress(resp.content).decode('utf-8', 'ignore')
            except Exception:
                # fallback: let requests guess
                return resp.text
        return resp.text

    def scrape_with_robust_retry(self, url: str) -> Optional[BeautifulSoup]:
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
        ]
        for i, ua in enumerate(user_agents):
            try:
                if i > 0:
                    time.sleep(random.uniform(2.0, 4.5))
                self.session.headers['User-Agent'] = ua
                st.info(f"Trying UA {i+1} for {url}")
                resp = self.session.get(url, timeout=20)
                resp.raise_for_status()
                html = self._decode_html(resp)
                if len(html) < 400:
                    st.warning("Got very short HTML; trying next UA…")
                    continue
                soup = BeautifulSoup(html, 'lxml')  # faster & more tolerant
                st.success(f"Fetched OK with UA {i+1}")
                return soup
            except Exception as e:
                st.warning(f"Attempt {i+1} failed: {e}")
        st.error("All attempts failed")
        return None

    def scrape_maynilad_tables(self, soup: BeautifulSoup) -> List[Dict]:
        interruptions = []
        try:
            tables = soup.find_all('table')
            st.info(f"Maynilad: found {len(tables)} <table> elements")
            # Path A: true tables
            for ti, table in enumerate(tables):
                rows = table.find_all('tr')
                if len(rows) <= 1:
                    continue
                for tr in rows[1:]:
                    cells = [td.get_text(" ", strip=True) for td in tr.find_all(['td','th'])]
                    if not cells: 
                        continue
                    row_text = " ".join(cells).lower()
                    if ('quezon city' in row_text) or re.search(r'\bqc\b', row_text):
                        interruptions.append({
                            'provider': 'Maynilad',
                            'source': 'table',
                            'raw_data': cells,
                            'description': " | ".join(cells),
                            'areas': ['Quezon City'],
                            'scraped_at': datetime.now()
                        })
    
            # Path B: Elementor/WordPress blocks (no <table>)
            if not interruptions:
                blocks = soup.select('.elementor-widget-container, article, .wp-block-group, .entry-content, .elementor-section')
                st.info(f"Maynilad: fallback blocks matched {len(blocks)}")
                for b in blocks:
                    text = b.get_text(" ", strip=True)
                    if not text or len(text) < 80:
                        continue
                    if re.search(r'\b(Quezon City|QC)\b', text, flags=re.I):
                        interruptions.append({
                            'provider': 'Maynilad',
                            'source': 'blocks',
                            'raw_data': text[:1000],
                            'description': text[:300],
                            'areas': ['Quezon City'],
                            'scraped_at': datetime.now()
                        })
    
            st.success(f"Maynilad QC interruptions: {len(interruptions)}")
        except Exception as e:
            st.error(f"Error parsing Maynilad: {e}")
        return interruptions


    def scrape_manila_water_table(self, soup: BeautifulSoup) -> List[Dict]:
        interruptions = []
        try:
            tables = soup.find_all('table')
            st.info(f"Manila Water: found {len(tables)} <table> elements")
            for table in tables:
                rows = table.find_all('tr')
                if len(rows) <= 1:
                    continue
                for tr in rows[1:]:
                    cells = [td.get_text(" ", strip=True) for td in tr.find_all(['td','th'])]
                    if not cells:
                        continue
                    text = " ".join(cells)
                    if re.search(r'\b(Quezon City|QC|Diliman|Fairview|Novaliches|Commonwealth)\b', text, flags=re.I):
                        interruptions.append({
                            'provider': 'Manila Water',
                            'source': 'table',
                            'raw_data': cells,
                            'description': " | ".join(cells),
                            'areas': ['Quezon City'],
                            'scraped_at': datetime.now()
                        })
    
            if not interruptions:
                # fallback to cards/lists
                cards = soup.select('.views-row, .card, article, .entry-content, .mw-advisory, .node')
                st.info(f"Manila Water: fallback blocks matched {len(cards)}")
                for c in cards:
                    text = c.get_text(" ", strip=True)
                    if len(text) < 80:
                        continue
                    if re.search(r'\b(Quezon City|QC|Diliman|Fairview|Novaliches|Commonwealth)\b', text, flags=re.I):
                        interruptions.append({
                            'provider': 'Manila Water',
                            'source': 'blocks',
                            'raw_data': text[:1000],
                            'description': text[:300],
                            'areas': ['Quezon City'],
                            'scraped_at': datetime.now()
                        })
    
            st.success(f"Manila Water QC interruptions: {len(interruptions)}")
        except Exception as e:
            st.error(f"Error parsing Manila Water: {e}")
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
