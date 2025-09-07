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
            '(02) 8863-0800',            # QCGH trunkline
            '(02) 928-0611',            # EAMC trunkline
            '(02) 8925-2401 to 50',     # PHC trunkline
            '(02) 927-6426 to 45',      # VMMC trunkline
            '(02) 8723-0101'            # St. Luke’s QC
        ],
        'type': 'Hospital',
        'lat': [14.6760, 14.6505, 14.6492, 14.6551, 14.6256],
        'lon': [121.0437, 121.0498, 121.0515, 121.0498, 121.0307]
    })
    
    # Sample evacuation centers
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
        'lon': [121.0498, 121.0498, 121.0565]
    })
    
    # Sample emergency services
    emergency_services = pd.DataFrame({
        'name': [
            'QC Fire Department - District 1',
            'QC Police Station - QCPD',
            'Philippine Red Cross QC',
            'QC Rescue 161',
            'QC Health Department'
        ],
        'address': [
            'East Avenue, Diliman, Quezon City',
            'Camp Karingal, Quezon City',
            'Scout Albano Street, Quezon City',
            'City Hall Complex, Quezon City',
            'City Hall Complex, Quezon City'
        ],
        'phone': [
            '(02) 8928-1234',
            '(02) 8806-4455',
            '(02) 8711-4785',
            '161',
            '(02) 8988-4242'
        ],
        'type': 'Emergency Service',
        'lat': [14.6505, 14.6712, 14.6278, 14.6507, 14.6507],
        'lon': [121.0498, 121.0356, 121.0267, 121.0498, 121.0498]
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

# Main app
def main():
    st.title("🚨 Quezon City Emergency Resource Locator")
    st.markdown("Find essential services and resources during weather emergencies in Quezon City")
    
    # Load data
    data = load_sample_data()
    
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
        st.subheader("🗺️ Resource Map")
        user_location = [user_lat, user_lon] if use_location else None
        map_obj = create_map(filtered_data, user_location)
        st_folium(map_obj, width=700, height=500)
    
    with col2:
        st.subheader("📋 Resource List")
        
        if use_location:
            st.markdown("*Sorted by distance from your location*")
        
        for idx, row in filtered_data.iterrows():
            with st.expander(f"{row['name']} ({row['type']})"):
                st.write(f"**Address:** {row['address']}")
                st.write(f"**Phone:** {row['phone']}")
                if use_location and 'distance_km' in row:
                    st.write(f"**Distance:** {row['distance_km']:.2f} km")
    
    # Emergency hotlines section
    st.markdown("---")
    st.subheader("🆘 Emergency Hotlines")
    
    emergency_numbers = {
        "QC Helpline (24/7)": "122",
        "QCDRRMO": "(02) 8927-5914 / (02) 8928-4396",
        "QC Trunkline": "(02) 8988-4242",
        "National Emergency Hotline": "911",
        "Philippine Red Cross (HQ)": "143 / (02) 8790-2300"
    }
    
    cols = st.columns(len(emergency_numbers))
    for i, (service, number) in enumerate(emergency_numbers.items()):
        with cols[i]:
            st.metric(service, number)
    
    # # Important notes
    # st.markdown("---")
    # st.warning("""
    # **Important Notes:**
    # - This is sample data for demonstration purposes only
    # - Always verify contact information before use in emergencies
    # - For life-threatening emergencies, call 911 immediately
    # - Data should be regularly updated with official sources
    # """)
    
    # # Data sources note
    # st.info("""
    # **Data Sources to Verify:**
    # - Quezon City Government Official Website
    # - Department of Health Hospital Directory
    # - NDRRMC Evacuation Center Database
    # - Local Government Unit Contact Lists
    # """)

if __name__ == "__main__":
    main()
