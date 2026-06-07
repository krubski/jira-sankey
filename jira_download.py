import requests
import json
import pandas as pd
import os
from datetime import datetime

#set variables
all_issues = []
next_page_token = None
max_results = 100

# Generate a clean, human-readable timestamp string (e.g., "June 07, 2026 at 04:30 PM EST")
# Note: GitHub Actions runs on UTC time, so we append "UTC" to be accurate
last_updated_str = datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC")

#Jira connection details
JIRA_URL = 'mkrubs.atlassian.net'
JIRA_EMAIL = 'mkrubs@gmail.com'
JIRA_TOKEN = 'ATATT3xFfGF0-fT3a4d3CVwZOf8lW6y1bWuHO3GxqTNzazuslc8DX_69zUMygkFCmwYXnxO7E0krtxGN8Yj14sNh1UTCtjsxPkinirCvBF_nIxVXV4lQaAfwj9-emF5T-pObbIaPWa5MK6y8f6DxnySdAN7eRjG8M_U-B8nOA3zVh535EFO5BO4=6E5B6D8E'
FILTER_ID = '10034'

url = f'https://{JIRA_URL}/rest/api/3/search/jql'

headers = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

auth = (JIRA_EMAIL, JIRA_TOKEN)

#Max Jira results is 100. Loop can return more than 100
while True:
    payload = {
        'jql': f'filter = {FILTER_ID}',
        'maxResults': max_results,
        'fields': [
            'summary',
            'status',
            'assignee',
            'customfield_10040',
            'customfield_10041',
            'customfield_10042',
        ],
    }

    #If we have a token from the previous loop, run payload
    if next_page_token:
        payload['nextPageToken'] = next_page_token

    response = requests.post(
        url, data=json.dumps(payload), headers=headers, auth=auth
    )

    #If response is good, begin to add data to batch
    if response.status_code == 200:
        #data is full results for current pull
        data = response.json()
        #batch is just issues results. .get() logic will return [] if there is an error
        batch = data.get('issues', [])

        #If batch is empty, end script
        if not batch:
            break

        #Add issues results to all_issues
        all_issues.extend(batch)
        print(f'-> Retrieved {len(all_issues)} issues...')

        #Grab the next cursor token from Jira's response
        next_page_token = data.get('nextPageToken')

        #If Jira doesn't return a new token, break.
        if not next_page_token:
            break
    #Return if error in response code
    else:
        print(f'Error fetching data from Jira: {response.status_code}')
        print(response.text)
        break

#Ensure we actually found records before proceeding
if all_issues:
    #Flatten into DataFrame and rename the data
    df = pd.json_normalize(all_issues)

    #Specify which columns to keep
    columns_to_keep = {
        'key': 'Issue Key',
        'fields.summary': 'Summary',
        'fields.status.name': 'Status',
        'fields.assignee.displayName': 'Assignee',
        'fields.customfield_10040': 'Job Title',
        'fields.customfield_10041': 'Company',
        'fields.customfield_10042.value': 'Source',
    }

    #Check to keep matches on columns and renames columns
    existing_columns = [
        col for col in columns_to_keep.keys() if col in df.columns
    ]
    df_clean = df[existing_columns].rename(columns=columns_to_keep)

    #Set the primary key for the DataFrame
    if 'Issue Key' in df_clean.columns:
        df_clean = df_clean.set_index('Issue Key')

    #Set order of the columns
    desired_order = [
        'Summary',
        'Status',
        'Assignee',
        'Job Title',
        'Company',
        'Source',
    ]
    df_clean = df_clean.reindex(columns=desired_order)

#    print(df_clean)

    #Convert types directly on df_clean to prep for Sankey
    df_clean['Source'] = df_clean['Source'].astype(str)
    df_clean['Status'] = df_clean['Status'].astype(str)

    #Aggregate data
    direct_flow = df_clean.groupby(['Source', 'Status']).size().reset_index(name='Weight')

    # --- ADD THESE TWO LINES TEMPORARILY ---
    print("👉 UNIQUE SOURCES (In Order):", sorted(df_clean['Source'].unique()))
    print("👉 UNIQUE STATUSES (In Order):", sorted(df_clean['Status'].unique()))
    
    #Convert into a List of Lists for JavaScript injection
    chart_data = direct_flow.values.tolist()

    print(chart_data)
    
    #Construct a multi-line f-string. This behaves like an HTML template file.
    html_template = f"""<!DOCTYPE html>
    <html>
    <head>
        <title>Jira Application Source Pipeline</title>
        <script type='text/javascript' src='https://www.gstatic.com/charts/loader.js'></script>
        <script type='text/javascript'>
        // Initialize and request the specific visualization packages we need
        google.charts.load('current', {{'packages':['sankey']}});
        google.charts.setOnLoadCallback(drawChart);

        function drawChart() {{
            var data = new google.visualization.DataTable();
            
            // Map the layout schema for Google Charts
            data.addColumn('string', 'Application Source');
            data.addColumn('string', 'Current Funnel Status');
            data.addColumn('number', 'Total Count');
            
            // Inject our native Python list object into the script brackets
            data.addRows({chart_data});

            // 1. HARDCODE YOUR EXACT COLOR MAP DICTIONARY
            // Explicitly links text strings directly to a hex color code.
            // Spelling matches your clean Jira strings perfectly!
            var colorMap = {{
            'Builtin': '#07006c',       // Builtin Dark Blue
            'Linkedin': '#0072b1',      // LinkedIn Blue
            'Me': '#27a6f5',            // Me Light Blue
            'Simplify': '#3bc4d7',      // Simplify Teal
            
            'Applied': '#2ecc71',       // Applied Green
            'No Response': '#f1c40f',   // No Response Yellow
            'Rejected': '#e74c3c'       // Rejected Red
            }};

            // 2. DYNAMICALLY BUILD THE COLOR PALETTE FOR GOOGLE CHARTS
            // Reads your live dataset layout, tracks node initialization order, 
            // and generates the corresponding color layout sequence dynamically.
            var dynamicColors = [];
            var coloredNodes = {{}}; 

            for (var i = 0; i < data.getNumberOfRows(); i++) {{
            var sourceNode = data.getValue(i, 0);
            var statusNode = data.getValue(i, 1);
            
            // Map Source color if unassigned
            if (!coloredNodes[sourceNode]) {{
                dynamicColors.push(colorMap[sourceNode] || '#cccccc'); // Fallback to gray if string is unmapped
                coloredNodes[sourceNode] = true;
            }}
            
            // Map Status color if unassigned
            if (!coloredNodes[statusNode]) {{
                dynamicColors.push(colorMap[statusNode] || '#cccccc'); // Fallback to gray if string is unmapped
                coloredNodes[statusNode] = true;
            }}
            }}

            // 3. Set layout configurations, sizing options, and inject the dynamic palette array
            var options = {{
            width: 950,
            height: 550,
            sankey: {{
                node: {{ 
                colors: dynamicColors, // Passes the beautifully mapped array right to the canvas
                label: {{ fontSize: 14, fontFamily: 'Arial', labelPadding: 15 }},
                padding: 35,
                interactivity: true
                }},
                link: {{ colorMode: 'gradient' }} // Blends node colors seamlessly across flow lines
            }}
            }};

            // Instantiate and display the chart container targeting our DOM container div id
            var chart = new google.visualization.Sankey(document.getElementById('sankey_view'));
            chart.draw(data, options);
        }}
        </script>
    </head>
    <body style='font-family: Arial, sans-serif; background-color: #f4f6f9; padding: 30px; display: flex; flex-direction: column; align-items: center;'>
        <div style='width: 950px; text-align: left; margin-bottom: 15px;'>
            <h2 style='color: #2c3e50; margin-bottom: 5px;'>Jira Application Source Pipeline</h2>
            <p style='color: #7f8c8d; margin-top: 0; font-size: 14px;'>
                Interactive Sankey mapping application channels straight to real-time funnel milestones.
                <span style='display: block; margin-top: 8px; color: #95a5a6; font-weight: bold;'>⏰ Last Synchronized: {last_updated_str}</span>
            </p>
        </div>
        
        <div id='sankey_view' style='width: 950px; height: 550px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); background: white; border-radius: 8px; padding: 15px;'></div>
    </body>
    </html>
    """

    #Open a local file workspace, enforce clean unicode string encoding, and save the web page
    with open("application_sankey.html", "w", encoding="utf-8") as file:
        file.write(html_template)

    print("\n🎉 ARCHITECTURE COMPILED SUCCESSFULLY!")
    print("-> Web asset written locally as 'application_sankey.html'")
    print("👉 Double-click 'application_sankey.html' inside your folder directory to launch your interactive dashboard!")