import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import math
from datetime import datetime

# Configure page
st.set_page_config(
    page_title="QC Emergency Resource Locator",
    page_icon="🚨",
    layout="wide"
)

# Sample data - Replace with verified QC data
@st.cache_data
def load_sample_data():
    # Hospitals (verified trunklines)
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
            '(02) 8863-0800',           # QCGH trunkline
            '(02) 928-0611',            # EAMC trunkline
            '(02) 8925-2401 to 50',     # PHC trunkline
            '(02) 927-6426 to 45',      # VMMC trunkline
            '(02) 8723-0101'            # St. Luke’s QC
        ],
        'type': 'Hospital',
        'lat': [14.6760, 14.6505, 14.6492, 14.6551, 14.6256],
        'lon': [121.0437, 121.0498, 121.0515, 121.0498, 121.0307]
    })

    # Emergency services (verified only)
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
            '(02) 8927-5914 / (02) 8928-4396',  # QCDRRMO
            '122',                              # QC Helpline (24/7)
            '143 / (02) 8790-2300'              # Red Cross national HQ hotline
        ],
        'type': 'Emergency Service',
        'lat': [14.6507, 14.6507, 14.5794],
