import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import math
from datetime import datetime
import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import re

# Load environment variables from .env file
load_dotenv()

# Get configuration from environment variables
SCRAPING_ENABLED = os.getenv('SCRAPING_ENABLED', 'true').lower() == 'true'
SCRAPING_INTERVAL_MINUTES = int(os.getenv('SCRAPING_INTERVAL_MINUTES', '30'))
MANILA_WATER_URL = os.getenv('MANILA_WATER_URL', 'https://www.manilawater.com/customers/service-advisories')
MAYNILAD_URL = os.getenv('MAYNILAD_URL', 'https://www.mayniladwater.com.ph/service-advisories-2/')
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
CACHE_TTL_HOURS = int(os.getenv('CACHE_TTL_HOURS', '1'))

# Configure page
st.set_page_config(
    page_title="QC Emergency Resource Locator",
    page_icon="🚨",
    layout="wide"
)

# Water Interruption Scraper Class
class WaterInterruptionScraper:
    def __init__(self):
        self.manila_water_url = MANILA_WATER_URL
        self.maynilad_url = MAYNILAD_URL
        
        # QC areas served by each company
        self.manila_water_qc_areas = [
            "Diliman", "UP Campus", "Quezon City Circle", "East Avenue",
            "Commonwealth", "Fairview", "Novaliches", "North Fairview",
            "La Mesa", "Tandang Sora", "Batasan Hills", "Payatas"
        ]
        
        self.maynilad_qc_areas = [
            "Project 6", "Cubao", "Kamias", "South Triangle",
            "Teachers Village", "Sikatuna Village", "Sacred Heart"
        ]

    def scrape_manila_water(self):
        """Scrape Manila Water interruption data"""
        if not SCRAPING_ENABLED:
            return []
            
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(self.manila_water_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            interruptions = []
            
            # Look for interruption announcements (adjust selectors based on actual site structure)
            interruption_items = soup.find_all(['div', 'tr'], class_=re.compile(r'interruption|advisory|announcement'))
            
            for item in interruption_items:
                text = item.get_text(strip=True)
                
                # Check if any QC area is mentioned
                qc_areas_mentioned = [area for area in self.manila_water_qc_areas 
                                    if area.lower() in text.lower()]
                
                if qc_areas_mentioned:
                    interruptions.append({
                        'provider': 'Manila Water',
                        'areas': qc_areas_mentioned,
                        'description': text[:200] + '...' if len(text) > 200 else text,
                        'scraped_at': datetime.now()
                    })
            
            return interruptions
            
        except Exception as e:
            if DEBUG_MODE:
                st.error(f"Error scraping Manila Water: {str(e)}")
            return []

    def scrape_maynilad(self):
        """Scrape Maynilad interruption data"""
        if not SCRAPING_ENABLED:
            return []
            
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(self.maynilad_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            interruptions = []
            
            # Look for interruption announcements
            interruption_items = soup.find_all(['div', 'tr'], class_=re.compile(r'interruption|advisory|announcement'))
            
            for item in interruption_items:
                text = item.get_text(strip=True)
                
                # Check if any QC area is mentioned
                qc_areas_mentioned = [area for area in self.maynilad_qc_areas 
                                    if area.lower() in text.lower()]
                
                if qc_areas_mentioned:
                    interruptions.append({
                        'provider': 'Maynilad',
                        'areas': qc_areas_mentioned,
                        'description': text[:200] + '...' if len(text) > 200 else text,
                        'scraped_at': datetime.now()
                    })
            
            return interruptions
            
        except Exception as e:
            if DEBUG_MODE:
                st.error(f"Error scraping Maynilad: {str(e)}")
            return []

    def get_all_qc_interruptions(self):
        """Get all water interruptions affecting QC"""
        all_interruptions = []
        
        # Scrape both providers
        manila_interruptions = self.scrape_manila_water()
        maynilad_interruptions = self.scrape_maynilad()
        
        all_interruptions.extend(manila_interruptions)
        all_interruptions.extend(maynilad_interruptions)
        
        return all_interruptions

# Cache water interruptions data
@st.cache_data(ttl=CACHE_TTL_HOURS*3600)  # Cache for specified hours
def get_water_interruptions():
    """Get cached water interruption data"""
    if not SCRAPING_ENABLED:
        return []
    
    scraper = WaterInterruptionScraper()
    return scraper.get_all_qc_interruptions()

# Sample data - Replace with verified QC data
@st.cache_data
def load_sample_data():
    # Sample hospitals data
    hospitals = pd.DataFrame({
        'name': [
            'Quezon City General Hospital',
            'East Avenue Medical Center',
            'Philippine Heart Center',
            'Veterans Memorial Medical Center',
            'St. Luke\'s Medical Center QC'
        ],
        'address': [
            'Seminary Rd, Quezon City',
            'East Avenue, Diliman, Quezon City',
            'East Avenue, Diliman, Quezon City',
            'North Avenue, Diliman, Quezon City',
            'E. Rodriguez Sr. Ave, Quezon City'
        ],
        'phone': [
            '(02) 8863-0800',            
            '(02) 928-0611',            
            '(02) 8925-2401 to 50',     
            '(02) 927-6426 to 45',      
            '(02) 8723-0101'            
        ],
        'type': 'Hospital',
        'lat': [14.6760, 14.6505, 14.6492, 14.6551, 14.6256],
        'lon': [121.0437, 121.0498, 121.0515, 121.0498, 121.0307]
    })
    
    # Sample evacuation centers
    evacuation_centers = pd.DataFrame({
        'name': [
            'Quezon City Hall Evacuation Center',
            'Diliman Elementary School',
            'Commonwealth Elementary School',
            'Novaliches High School',
            'Fairview Elementary School'
        ],
        'address': [
            'Elliptical Road, Diliman, Quezon City',
            'Roces Avenue, Diliman, Quezon City',
            'Commonwealth Avenue, Quezon City',
            'Novaliches, Quezon City',
            'Fairview, Quezon City'
        ],
        'phone': [
            '(02) 8988-4242',
            '(02) 8921-2345',
            '(02) 8951-1234',
            '(02) 8931-5678',
            '(02) 8941-9876'
        ],
        'type': 'Evacuation Center',
        'lat': [14.6507, 14.6548, 14.7123, 14.7281, 14.7612],
        'lon': [121.0498, 121.0689, 121.0789, 121.0456, 121.0623]
    })
    
    # Sample emergency services
    emergency_services = pd.DataFrame({
        'name': [
            'QCDRRMO',
            'Quezon City Helpline',
            'Philippine Red Cross (HQ)'
        ],
        'address': [
            'Quezon City Hall Complex, Quezon City',
            'Quezon City Government',
            '37 EDSA corner Boni Ave, Mandaluyong (HQ)'
        ],
        'phone': [
            os.getenv('QCDRRMO_PHONE', '(02) 8927-5914'),
            os.getenv('QC_HELPLINE', '122'),
            '143 / (02) 8790-2300'
        ],
        'type': 'Emergency Service',
        'lat': [14.6507, 14.6507, 14.5794],
        'lon': [121.0498, 121.0498, 121.0565]
    })

    return pd.concat([hospitals, evacuation_centers, emergency_services], ignore_index=True)

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points using Haversine formula"""
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

def create_map(data, user_location=None):
    """Create a folium map with resource markers"""
    # Center map on QC
    center_lat = 14.6760
    center_lon = 121.0437
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
    
    # Color coding for different resource types
    colors = {
        'Hospital': 'red',
        'Evacuation Center': 'blue',
        'Emergency Service': 'green'
    }
    
    # Add markers for each resource
    for idx, row in data.iterrows():
        folium.Marker(
            location=[row['lat'], row['lon']],
            popup=folium.Popup(
                f"<b>{row['name']}</b><br>"
                f"Type: {row['type']}<br>"
                f"Address: {row['address']}<br>"
                f"Phone: {row['phone']}",
                max_width=300
            ),
            tooltip=row['name'],
            icon=folium.Icon(color=colors.get(row['type'], 'gray'))
        ).add_to(m)
    
    # Add user location if provided
    if user_location:
        folium.Marker(
            location=user_location,
            popup="Your Location",
            icon=folium.Icon(color='orange', icon='user')
        ).add_to(m)
    
    return m

def display_water_interruptions():
    """Display water interruption section"""
    st.subheader("💧 Water Service Interruptions")
    
    if SCRAPING_ENABLED:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write("Checking for water service interruptions in QC areas...")
        with col2:
            if st.button("🔄 Refresh", key="refresh_water"):
                st.cache_data.clear()
        
        with st.spinner("Loading water service status..."):
            interruptions = get_water_interruptions()
        
        if interruptions:
            st.warning(f"⚠️ {len(interruptions)} water service interruptions affecting QC areas")
            
            for interruption in interruptions:
                with st.expander(f"{interruption['provider']} - {', '.join(interruption['areas'])}"):
                    st.write(f"**Provider:** {interruption['provider']}")
                    st.write(f"**Affected QC Areas:** {', '.join(interruption['areas'])}")
                    st.write(f"**Details:** {interruption['description']}")
                    st.write(f"**Last Updated:** {interruption['scraped_at'].strftime('%Y-%m-%d %H:%M')}")
        else:
            st.success("✅ No water interruptions currently reported for QC areas")
    else:
        st.info("💧 Water interruption monitoring is currently disabled")

# Main app
def main():
    st.title("🚨 Quezon City Emergency Resource Locator")
    st.markdown("Find essential services and resources during weather emergencies in Quezon City")
    
    # Show debug info if enabled
    if DEBUG_MODE:
        st.sidebar.markdown("### 🔧 Debug Info")
        st.sidebar.json({
            "scraping_enabled": SCRAPING_ENABLED,
            "scraping_interval": SCRAPING_INTERVAL_MINUTES,
            "cache_ttl_hours": CACHE_TTL_HOURS,
            "manila_water_url": MANILA_WATER_URL[:50] + "...",
            "maynilad_url": MAYNILAD_URL[:50] + "..."
        })
    
    # Load data
    data = load_sample_data()
    
    # Water interruptions section (new!)
    display_water_interruptions()
    st.markdown("---")
    
    # Sidebar for filters and location input
    st.sidebar.header("🔍 Search & Filter")
    
    # Resource type filter
    resource_types = st.sidebar.multiselect(
        "Select Resource Types:",
        options=data['type'].unique(),
        default=data['type'].unique()
    )
    
    # Location input
    st.sidebar.subheader("📍 Your Location (Optional)")
    user_lat = st.sidebar.number_input("Latitude", value=14.6507, format="%.6f")
    user_lon = st.sidebar.number_input("Longitude", value=121.0498, format="%.6f")
    use_location = st.sidebar.checkbox("Use my location for distance calculation")
    
    # Filter data based on selection
    filtered_data = data[data['type'].isin(resource_types)]
    
    # Calculate distances if user location is provided
    if use_location:
        filtered_data = filtered_data.copy()
        filtered_data['distance_km'] = filtered_data.apply(
            lambda row: calculate_distance(user_lat, user_lon, row['lat'], row['lon']),
            axis=1
        )
        filtered_data = filtered_data.sort_values('distance_km')
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Resource Map")
        user_location = [user_lat, user_lon] if use_location else None
        map_obj = create_map(filtered_data, user_location)
        st_folium(map_obj, width=700, height=500)
    
    with col2:
        st.subheader("Resource List")
        
        if use_location:
            st.markdown("*Sorted by distance from your location*")
        
        # Get unique resource types
        resource_types_available = filtered_data['type'].unique()
        
        # Create columns for each resource type
        if len(resource_types_available) > 0:
            cols = st.columns(min(len(resource_types_available), 3))  # Max 3 columns
            
            for i, resource_type in enumerate(resource_types_available):
                with cols[i % 3]:  # Cycle through columns if more than 3 types
                    st.markdown(f"**{resource_type}s**")
                    
                    # Filter data for this resource type
                    type_data = filtered_data[filtered_data['type'] == resource_type]
                    
                    for idx, row in type_data.iterrows():
                        with st.expander(f"{row['name']}"):
                            st.write(f"**Address:** {row['address']}")
                            st.write(f"**Phone:** {row['phone']}")
                            if use_location and 'distance_km' in row:
                                st.write(f"**Distance:** {row['distance_km']:.2f} km")
    
    # Emergency hotlines section
    st.markdown("---")
    st.subheader("Emergency Hotlines")
    
    emergency_numbers = {
        "QC Helpline (24/7)": os.getenv('QC_HELPLINE', '122'),
        "QCDRRMO": os.getenv('QCDRRMO_PHONE', '(02) 8927-5914'),
        "QC Trunkline": "(02) 8988-4242",
        "National Emergency Hotline": "911",
        "Philippine Red Cross (HQ)": "143"
    }
    
    cols = st.columns(len(emergency_numbers))
    for i, (service, number) in enumerate(emergency_numbers.items()):
        with cols[i]:
            st.metric(service, number)

if __name__ == "__main__":
    main()
