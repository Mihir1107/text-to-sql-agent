import os
import sys

# Add the current directory to sys.path so app.* imports work correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import everything from the actual streamlit app to allow 'streamlit run streamlit_app.py'
from ui.streamlit_app import *
