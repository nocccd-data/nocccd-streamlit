import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re
import os
import json
from collections import Counter

# Set page configuration
st.set_page_config(
    page_title="Winter Student Survey Results",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Add a title and description
st.title("Winter Student Survey Results")
st.write("This dashboard presents the results of the Winter Student Survey conducted on March 10, 2025.")
# Add author information to the sidebar
st.sidebar.image("src/static/NOCCCD Logo.jpg", use_container_width=True)
st.sidebar.markdown('---')  # Add a horizontal line for separation
st.sidebar.markdown('**Author:** Jihoon Ahn <jahn@noccd.edu>')

# Function to extract question groups from the original CSV
@st.cache_data
def load_data():
    try:
        # Try multiple possible file paths for Docker environment
        possible_paths = [
            "/app/src/data/Winter Student Survey_March 10, 2025_14.33.csv",
            "/app/data/Winter Student Survey_March 10, 2025_14.33.csv",
            "/data/Winter Student Survey_March 10, 2025_14.33.csv",
            "data/Winter Student Survey_March 10, 2025_14.33.csv",
            "../data/Winter Student Survey_March 10, 2025_14.33.csv",
            "../../data/Winter Student Survey_March 10, 2025_14.33.csv",
            "Winter Student Survey_March 10, 2025_14.33.csv"
        ]
        
        # Try each path until one works
        file_path = None
        for path in possible_paths:
            if os.path.exists(path):
                file_path = path
                st.sidebar.success(f"Found data file at: {path}")
                break
        
        if file_path is None:
            # Last resort: Try to find the file anywhere in the filesystem
            st.sidebar.warning("Searching for data file in common locations...")
            
            search_paths = [
                "/app",
                "/app/src",
                "/app/src/scripts",
                "/app/src/data",
                "/data",
                "."
            ]
            
            for search_path in search_paths:
                if os.path.exists(search_path):
                    for root, dirs, files in os.walk(search_path):
                        for file in files:
                            if "Winter Student Survey" in file and file.endswith(".csv"):
                                file_path = os.path.join(root, file)
                                st.sidebar.success(f"Found data file at: {file_path}")
                                break
                        if file_path:
                            break
                if file_path:
                    break
        
        if file_path is None:
            st.error("Could not find the data file. Please check the file paths.")
            st.sidebar.error("Data file not found. Please update the file path.")
            # Return empty dataframes to prevent errors - IMPORTANT: Return 5 values to match unpacking
            return pd.DataFrame(), {}, {}, {}, {}
        
        # Read the first three rows to get the headers
        df_raw = pd.read_csv(file_path, header=None, nrows=3)
        
        # Extract the headers - row 0 contains friendly names, row 1 contains questions, row 2 contains QIDs
        friendly_names_row = df_raw.iloc[0].tolist()
        questions_row = df_raw.iloc[1].tolist()
        qids_row = df_raw.iloc[2].tolist()
        
        # Read the data (skipping the first 3 rows)
        df_data = pd.read_csv(file_path, skiprows=3)
        
        # Extract QIDs from the JSON format
        qids = []
        for qid_raw in qids_row:
            try:
                if isinstance(qid_raw, str) and '{"ImportId":"' in qid_raw:
                    # Parse the JSON string to extract the QID
                    match = re.search(r'"ImportId":"(.*?)"', qid_raw)
                    if match:
                        qid = match.group(1)
                        qids.append(qid)
                    else:
                        qids.append(str(qid_raw))
                else:
                    qids.append(str(qid_raw))
            except Exception as e:
                qids.append(str(qid_raw))
        
        # Create question mapping
        question_mapping = {}
        for i in range(len(qids)):
            if i < len(questions_row):
                question_mapping[qids[i]] = questions_row[i]
        
        # Create a mapping from QID group to friendly name
        friendly_name_mapping = {}
        
        # Track text-based questions separately
        text_questions = {}
        
        # Group questions by QID prefix
        question_groups = {}
        for i, qid in enumerate(qids):
            if isinstance(qid, str) and qid.startswith('QID'):
                # Check if this is a text-based question
                is_text_question = qid.endswith('_TEXT')
                
                # Extract the group number (e.g., QID16 from QID16_1)
                match = re.match(r'(QID\d+)', qid)
                if match:
                    group_key = match.group(1)
                    
                    # Get friendly name from row 0 if available
                    if i < len(friendly_names_row) and pd.notna(friendly_names_row[i]):
                        friendly_name = str(friendly_names_row[i])
                        
                        # Clean up the friendly name
                        # Remove numeric suffixes like _1, _2, etc.
                        friendly_name = re.sub(r'_\d+$', '', friendly_name)
                        
                        # Handle special cases like Q1, Q4_1
                        if friendly_name.startswith('Q') and re.match(r'Q\d+(_\d+)?$', friendly_name):
                            # Extract just the Q number part
                            q_match = re.match(r'(Q\d+)', friendly_name)
                            if q_match:
                                friendly_name = q_match.group(1)
                        
                        # Capitalize first letter of each word
                        friendly_name = friendly_name.title()
                        
                        # Store in mapping
                        friendly_name_mapping[group_key] = friendly_name
                    
                    # For text questions, store them separately
                    if is_text_question:
                        if qid in ["QID23_TEXT", "QID25_TEXT", "QID21_TEXT", "QID12_TEXT"]:
                            if i < len(questions_row):
                                question_text = str(questions_row[i])
                                text_questions[qid] = {
                                    'question': question_text,
                                    'qid': qid,
                                    'column_index': i
                                }
                        continue  # Skip adding text questions to regular question groups
                    
                    if group_key not in question_groups:
                        question_groups[group_key] = []
                    
                    if i < len(questions_row):
                        # Extract the specific question part after the group question
                        full_question = str(questions_row[i])
                        
                        # For grouped questions, they often have a format like "Group question? - Specific question"
                        parts = full_question.split(' - ', 1)
                        specific_question = parts[1] if len(parts) > 1 else full_question
                        group_question = parts[0] if len(parts) > 1 else ""
                        
                        question_groups[group_key].append({
                            'qid': qid,
                            'full_question': full_question,
                            'specific_question': specific_question,
                            'group_question': group_question
                        })
        
        # Map the QIDs to the dataframe columns
        # First, get the original column names
        original_columns = df_data.columns.tolist()
        
        # Create a mapping from original column names to QIDs
        column_to_qid = {}
        for i, col in enumerate(original_columns):
            if i < len(qids):
                column_to_qid[col] = qids[i]
        
        # Rename the dataframe columns to use QIDs
        df_data.rename(columns=column_to_qid, inplace=True)
        
        return df_data, question_mapping, question_groups, friendly_name_mapping, text_questions
    
    except Exception as e:
        st.error(f"Error loading data: {e}")
        import traceback
        st.sidebar.error(f"Traceback: {traceback.format_exc()}")
        # IMPORTANT: Return 5 values to match unpacking
        return pd.DataFrame(), {}, {}, {}, {}

# Define standard color palettes for different response types
color_palettes = {
    "importance": {
        "Very Important": "#4C78A8",
        "Important": "#72B7B2",
        "Somewhat Important": "#54A24B",
        "Not Important": "#F2C14E"
    },
    "agreement": {
        "Strongly Agree": "#4C78A8",
        "Agree": "#72B7B2",
        "Neutral": "#54A24B",
        "Disagree": "#F2C14E",
        "Strongly Disagree": "#E45756"
    },
    "difficulty": {
        "Very easy": "#4C78A8",
        "Somewhat easy": "#72B7B2",
        "Neutral": "#54A24B",
        "Somewhat difficult": "#F2C14E",
        "Very difficult": "#E45756",
        "Not applicable/Did not use service": "#9D755D"
    },
    "satisfaction": {
        "Very Satisfied": "#4C78A8",
        "Satisfied": "#72B7B2",
        "Neutral": "#54A24B",
        "Dissatisfied": "#F2C14E",
        "Very Dissatisfied": "#E45756"
    },
    # Default colorful palette for other response types
    "default": [
        "#4C78A8", "#72B7B2", "#54A24B", "#F2C14E", "#E45756", 
        "#FF9E4A", "#EECA3B", "#B279A2", "#FF9DA6", "#9D755D"
    ]
}

# Function to create a combined horizontal bar chart for a question group
def create_group_bar_chart(df, questions, group_key):
    try:
        # Check if this is a single-question group
        is_single_question = len(questions) == 1
        
        # Extract the group question from the first question
        group_question = None
        if questions and 'group_question' in questions[0]:
            group_question = questions[0]['group_question']
        
        if not group_question:
            group_question = "Question Group"
        
        # Get all the specific questions and their QIDs
        specific_questions = []
        qids = []
        for question in questions:
            if 'specific_question' in question and 'qid' in question:
                # Skip text-based questions (QIDs ending with '_TEXT')
                if question['qid'].endswith('_TEXT'):
                    continue
                specific_questions.append(question['specific_question'])
                qids.append(question['qid'])
        
        if not specific_questions:
            st.warning("No specific questions found in this group.")
            return None
        
        # For single-question groups, use the full question as the title
        chart_title = ""
        if is_single_question and 'full_question' in questions[0]:
            chart_title = questions[0]['full_question']
            # For single questions, we'll use an empty label on the y-axis
            specific_questions = [""]
        else:
            chart_title = group_question
        
        # Get all possible response categories across all questions in the group
        all_categories = set()
        for qid in qids:
            if qid in df.columns:
                unique_responses = df[qid].dropna().unique()
                all_categories.update(unique_responses)
        
        # Order responses in a meaningful way based on common survey response formats
        ordered_responses = [
            "Very Important", "Important", "Somewhat Important", "Not Important", 
            "Strongly Agree", "Agree", "Neutral", "Disagree", "Strongly Disagree",
            "Very easy", "Somewhat easy", "Neutral", "Somewhat difficult", "Very difficult",
            "Very Satisfied", "Satisfied", "Neutral", "Dissatisfied", "Very Dissatisfied",
            "Not applicable/Did not use service"
        ]
        
        # Get the ordered categories
        ordered_categories = [r for r in ordered_responses if r in all_categories]
        unordered_extras = [r for r in all_categories if r not in ordered_responses]
        final_categories = ordered_categories + unordered_extras
        
        # Determine which color palette to use based on the categories
        palette_type = "default"
        if any(cat in ["Very Important", "Important", "Somewhat Important", "Not Important"] for cat in all_categories):
            palette_type = "importance"
        elif any(cat in ["Strongly Agree", "Agree", "Disagree", "Strongly Disagree"] for cat in all_categories):
            palette_type = "agreement"
        elif any(cat in ["Very easy", "Somewhat easy", "Somewhat difficult", "Very difficult"] for cat in all_categories):
            palette_type = "difficulty"
        elif any(cat in ["Very Satisfied", "Satisfied", "Dissatisfied", "Very Dissatisfied"] for cat in all_categories):
            palette_type = "satisfaction"
        
        # Create a color list for the responses
        if palette_type == "default":
            # Use the default color list and cycle through it
            default_colors = color_palettes["default"]
            color_list = [default_colors[i % len(default_colors)] for i in range(len(final_categories))]
        else:
            # Use the specific palette
            palette = color_palettes[palette_type]
            color_list = [palette.get(cat, "#9D755D") for cat in final_categories]
        
        # Prepare data for the chart
        data = []
        for i, qid in enumerate(qids):
            if qid in df.columns:
                # Count responses for this question
                response_counts = df[qid].value_counts(dropna=True).to_dict()
                
                # Create a row for each category
                row = []
                for category in final_categories:
                    row.append(float(response_counts.get(category, 0)))  # Convert to float to avoid int64 issues
                
                data.append(row)
            else:
                # If QID not found, add zeros
                data.append([0.0] * len(final_categories))  # Use floats instead of integers
        
        # Convert to numpy array with float dtype to avoid int64 issues
        data = np.array(data, dtype=float)
        
        # Calculate percentages - ensure we're working with floats
        row_sums = data.sum(axis=1, keepdims=True)
        # Handle division by zero safely
        data_percent = np.zeros_like(data)
        for i in range(len(data)):
            if row_sums[i] > 0:
                data_percent[i] = (data[i] / row_sums[i]) * 100
        
        # Create the figure
        fig = go.Figure()
        
        # Add bars for each category
        for i, category in enumerate(final_categories):
            fig.add_trace(go.Bar(
                y=specific_questions,
                x=data_percent[:, i],
                name=category,
                orientation='h',
                marker=dict(color=color_list[i]),
                text=[f"{p:.1f}%" if p > 3 else "" for p in data_percent[:, i]],
                textposition='inside',
                insidetextanchor='middle',
                customdata=data[:, i],
                hovertemplate='%{customdata} responses (%{x:.1f}%)<extra>%{fullData.name}</extra>'
            ))
        
        # Update layout
        fig.update_layout(
            title=dict(
                text=chart_title,
                y=1,  # Move title up to create more space
                x=0,
                xanchor='auto',
                yanchor='top'
            ),
            barmode='stack',
            height=max(300, len(specific_questions) * 40),
            margin=dict(l=20, r=20, t=80, b=20),  # Increase top margin for legend
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.05,             # Position of legend relative to the chart
                xanchor="center",        # Change from "right" to "center" for better centering
                x=0.5,                 # Center the legend horizontally (change from x=1)
                traceorder="normal",    
                itemwidth=30,  # Control width of legend items
                itemsizing="constant"  # Keep item sizes consistent
            ),
            xaxis=dict(
                title='Percentage of Responses',
                range=[0, 100]
            ),
            yaxis=dict(
                title=None,
                automargin=True,
                # For single questions, hide the y-axis labels
                showticklabels=not is_single_question
            )
        )
        
        return fig
    
    except Exception as e:
        st.error(f"Error creating chart: {e}")
        import traceback
        st.error(f"Detailed error: {traceback.format_exc()}")
        return None
    
# Function to display text responses in an expander with grouping
def display_text_responses(df, text_question_info):
    try:
        qid = text_question_info['qid']
        question = text_question_info['question']
        
        # Extract the base QID (without _TEXT)
        base_qid = qid.replace('_TEXT', '')
        
        # Get friendly name if available
        friendly_name = friendly_name_mapping.get(base_qid, base_qid)
        
        # Create an expander for this text question
        with st.expander(f"{friendly_name}: {question}"):
            if qid in df.columns:
                # Get all non-empty responses
                responses = df[qid].dropna().tolist()
                
                if responses:
                    # Group identical responses and count occurrences
                    response_counts = Counter(responses)
                    
                    # Display each unique response with count if more than 1
                    for response, count in response_counts.items():
                        if count > 1:
                            st.markdown(f"**{response}** *(mentioned {count} times)*")
                        else:
                            st.markdown(f"{response}")
                        st.markdown("---")
                else:
                    st.info("No text responses provided for this question.")
            else:
                st.warning(f"Column {qid} not found in the data.")
    except Exception as e:
        st.error(f"Error displaying text responses: {e}")
        import traceback
        st.error(f"Detailed error: {traceback.format_exc()}")

# Load the data - IMPORTANT: Make sure to unpack 5 values
df_data, question_mapping, question_groups, friendly_name_mapping, text_questions = load_data()

# Sidebar for navigation
st.sidebar.title("Navigation")

# Create a list of options with friendly names
group_options = list(question_groups.keys())
friendly_options = []
for group_key in group_options:
    friendly_name = friendly_name_mapping.get(group_key, group_key)
    friendly_options.append((group_key, friendly_name))

# Sort by friendly name
friendly_options.sort(key=lambda x: x[1])

# Add a section for text responses in the sidebar
has_text_responses = len(text_questions) > 0
if has_text_responses:
    friendly_options.append(("text_responses", "Text Responses"))

# Option to select a specific question group
if friendly_options:
    # Create a list of friendly names for the dropdown
    dropdown_options = ["All Groups"] + [friendly_name for _, friendly_name in friendly_options]
    
    # Create a mapping from friendly name back to group key
    friendly_to_key = {friendly_name: group_key for group_key, friendly_name in friendly_options}
    friendly_to_key["All Groups"] = "All Groups"
    
    selected_friendly = st.sidebar.selectbox(
        "Select Question Group",
        options=dropdown_options
    )
    
    # Convert the selected friendly name back to the group key
    selected_group = friendly_to_key[selected_friendly]
    
    # Display the selected group or all groups
    if selected_group == "All Groups":
        # First display all chart groups
        for group_key, questions in question_groups.items():
            # Filter out any groups that might only contain TEXT questions
            filtered_questions = [q for q in questions if not q['qid'].endswith('_TEXT')]
            if not filtered_questions:
                continue
            
            # Get the friendly name for this group
            friendly_name = friendly_name_mapping.get(group_key, group_key)
                
            st.subheader(f"Question Group: {friendly_name}")
            fig = create_group_bar_chart(df_data, filtered_questions, group_key)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
                
                # Add response details
                total_responses = len(df_data)
                st.caption(f"Total respondents: {total_responses}")
                
                # Add a separator
                st.markdown("---")
        
        # Then display text responses section if there are any
        if has_text_responses:
            st.header("Text Responses")
            st.write("Expandable sections below contain open-ended text responses from the survey.")
            
            # Display each text question in an expander
            for qid, text_info in text_questions.items():
                display_text_responses(df_data, text_info)
    
    elif selected_group == "text_responses":
        # Display only the text responses section
        st.header("Text Responses")
        st.write("Expandable sections below contain open-ended text responses from the survey.")
        
        # Display each text question in an expander
        for qid, text_info in text_questions.items():
            display_text_responses(df_data, text_info)
    
    else:
        # Get the friendly name for this group
        friendly_name = friendly_name_mapping.get(selected_group, selected_group)
        
        st.subheader(f"Question Group: {friendly_name}")
        # Filter out any TEXT questions
        filtered_questions = [q for q in question_groups[selected_group] if not q['qid'].endswith('_TEXT')]
        if filtered_questions:
            fig = create_group_bar_chart(df_data, filtered_questions, selected_group)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
                
                # Add response details
                total_responses = len(df_data)
                st.caption(f"Total respondents: {total_responses}")
        else:
            st.info("This question group contains only open-ended text responses, which are not visualized in charts.")
else:
    st.warning("No question groups found in the data. Please check the file path and format.")
    st.sidebar.warning("No question groups found.")

# Add information about the data
st.sidebar.markdown("---")
st.sidebar.info(
    "This dashboard visualizes data from the Winter Student Survey conducted on March 10, 2025. "
    "The survey collected responses from students about their experiences and motivations for taking winter classes."
)

# Footer
st.markdown("---")
st.markdown("Winter Student Survey Results Dashboard | Created with Streamlit")
