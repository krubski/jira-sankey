import requests
import json
import pandas as pd
import os
from datetime import datetime, timezone

# Set variables
all_issues = []
next_page_token = None
max_results = 100

# Grab the exact frozen moment the script runs in the cloud in raw ISO format for JavaScript conversion
current_utc_iso = datetime.now(timezone.utc).isoformat()

# Jira connection details
JIRA_URL = os.environ.get('JIRA_URL')
JIRA_EMAIL = os.environ.get('JIRA_EMAIL')
JIRA_TOKEN = os.environ.get('JIRA_TOKEN') 
JIRA_FILTER_ID = os.environ.get('JIRA_FILTER_ID')

url = f'https://{JIRA_URL}/rest/api/3/search/jql'

headers = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

auth = (JIRA_EMAIL, JIRA_TOKEN)

# Max Jira results is 100. Loop can return more than 100
while True:
    payload = {
        'jql': f'filter = {JIRA_FILTER_ID}',
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

    # If we have a token from the previous loop, run payload
    if next_page_token:
        payload['nextPageToken'] = next_page_token

    response = requests.post(
        url, data=json.dumps(payload), headers=headers, auth=auth
    )

    # If response is good, begin to add data to batch
    if response.status_code == 200:
        data = response.json()
        batch = data.get('issues', [])

        # If batch is empty, end script
        if not batch:
            break

        # Add issues results to all_issues
        all_issues.extend(batch)
        print(f'-> Retrieved {len(all_issues)} issues...')

        # Grab the next cursor token from Jira's response
        next_page_token = data.get('nextPageToken')

        # If Jira doesn't return a new token, break.
        if not next_page_token:
            break
    # Return if error in response code
    else:
        print(f'Error fetching data from Jira: {response.status_code}')
        print(response.text)
        break

# Ensure we actually found records before proceeding
if all_issues:
    # Flatten into DataFrame and rename the data
    df = pd.json_normalize(all_issues)

    # Specify which columns to keep
    columns_to_keep = {
        'key': 'Issue Key',
        'fields.summary': 'Summary',
        'fields.status.name': 'Status',
        'fields.assignee.displayName': 'Assignee',
        'fields.customfield_10040': 'Job Title',
        'fields.customfield_10041': 'Company',
        'fields.customfield_10042.value': 'Source',
    }

    # Check to keep matches on columns and renames columns
    existing_columns = [
        col for col in columns_to_keep.keys() if col in df.columns
    ]
    df_clean = df[existing_columns].rename(columns=columns_to_keep)

    # Set the primary key for the DataFrame
    if 'Issue Key' in df_clean.columns:
        df_clean = df_clean.set_index('Issue Key')

    # Set order of the columns
    desired_order = [
        'Summary',
        'Status',
        'Assignee',
        'Job Title',
        'Company',
        'Source',
    ]
    df_clean = df_clean.reindex(columns=desired_order)

    # Convert types directly to string to prep for aggregation
    df_clean['Source'] = df_clean['Source'].astype(str)
    df_clean['Status'] = df_clean['Status'].astype(str)

    # =========================================================================
    # 🌟 TRACKABLE SOURCE-SPECIFIC END-TO-END FLOW LOGIC
    # =========================================================================
    pipeline_rows = []

    for _, row in df_clean.iterrows():
        source = row['Source']
        status = row['Status']
        
        # Standardize source names to fix casing mismatches
        if source.lower() == 'linkedin':
            source = 'LinkedIn'
        elif source.lower() == 'builtin':
            source = 'Builtin'
        elif source.lower() == 'networking':
            source = 'Networking'
            
        middle_node = f"{source} (Applied)"

        # --- CONDITION 1: Active "Applied" items ---
        if status == 'Applied':
            pipeline_rows.append({'Source': source, 'Target': middle_node, 'Weight': 1})

        # --- CONDITION 2: "No Response" items ---
        elif status == 'No Response':
            pipeline_rows.append({'Source': source, 'Target': middle_node, 'Weight': 1})
            pipeline_rows.append({'Source': middle_node, 'Target': 'No Response', 'Weight': 1})

        # --- CONDITION 3: "Application Rejected" items ---
        elif status == 'Application Rejected':
            pipeline_rows.append({'Source': source, 'Target': middle_node, 'Weight': 1})
            pipeline_rows.append({'Source': middle_node, 'Target': 'Application Rejected', 'Weight': 1})

    # Convert row entries into a clean DataFrame and aggregate the totals
    if pipeline_rows:
        final_pipeline = pd.DataFrame(pipeline_rows)
        final_pipeline = final_pipeline.groupby(['Source', 'Target']).size().reset_index(name='Weight')
        
        # Sort values cleanly by data lineage
        final_pipeline = final_pipeline.sort_values(by=['Source', 'Target'], ascending=[True, True])
        chart_data = final_pipeline.values.tolist()
    else:
        chart_data = []
    # =========================================================================

    print("👉 Outputting Aligned 3-Line Layout to Dashboard...")
    
    # Construct a multi-line f-string. This behaves like an HTML template file.
    html_template = f"""<!DOCTYPE html>
    <html>
    <head>
        <title>Jira Application Source Pipeline</title>
        <script type='text/javascript' src='https://www.gstatic.com/charts/loader.js'></script>
        <script type='text/javascript'>
        google.charts.load('current', {{'packages':['sankey']}});
        google.charts.setOnLoadCallback(drawChart);

        function drawChart() {{
            var data = new google.visualization.DataTable();
            
            data.addColumn('string', 'From Node');
            data.addColumn('string', 'To Node');
            data.addColumn('number', 'Total Count');
            
            data.addRows({chart_data});

            // HARDCODE COLOR MAP DICTIONARY
            var colorMap = {{
            'Builtin': '#07006c',
            'LinkedIn': '#0072b1',
            'Me': '#27a6f5',
            'Networking': '#fa9214',
            'Simplify': '#3bc4d7',
            
            'Builtin (Applied)': '#07006c',
            'LinkedIn (Applied)': '#0072b1',
            'Me (Applied)': '#27a6f5',
            'Networking (Applied)': '#fa9214',
            'Simplify (Applied)': '#3bc4d7',
            
            'No Response': '#f1c40f',
            'Application Rejected': '#e74c3c'
            }};

            // DYNAMICALLY BUILD THE COLOR PALETTE FOR GOOGLE CHARTS
            var dynamicColors = [];
            var coloredNodes = {{}}; 

            for (var i = 0; i < data.getNumberOfRows(); i++) {{
                var sourceNode = data.getValue(i, 0);
                var statusNode = data.getValue(i, 1);
                
                if (!coloredNodes[sourceNode]) {{
                    dynamicColors.push(colorMap[sourceNode] || '#cccccc');
                    coloredNodes[sourceNode] = true;
                }}
                if (!coloredNodes[statusNode]) {{
                    dynamicColors.push(colorMap[statusNode] || '#cccccc');
                    coloredNodes[statusNode] = true;
                }}
            }}

            var options = {{
            width: 950,
            height: 550,
            sankey: {{
                node: {{ 
                colors: dynamicColors,
                label: {{ fontSize: 14, fontFamily: 'Arial', labelPadding: 15 }},
                padding: 35,
                interactivity: true
                }},
                link: {{ colorMode: 'gradient' }}
            }}
            }};

            var chart = new google.visualization.Sankey(document.getElementById('sankey_view'));
            chart.draw(data, options);
        }}
        </script>
    </head>
    <body style='font-family: Arial, sans-serif; background-color: #f4f6f9; padding: 30px; display: flex; flex-direction: column; align-items: center;'>
        <div style='width: 950px; text-align: left; margin-bottom: 15px;'>
            <h2 style='color: #2c3e50; margin-bottom: 5px;'>Jira Application Source Pipeline</h2>
            <p style='color: #7f8c8d; margin-top: 0; font-size: 14px;'>
                Interactive Sankey mapping application channels straight to real-time outcomes.
                <span style='display: block; margin-top: 8px; color: #95a5a6; font-weight: bold;'>
                    ⏰ Last Synchronized: <span id="local-timestamp">Calculating local time...</span>
                </span>
            </p>
        </div>
        
        <div id='sankey_view' style='width: 950px; height: 550px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); background: white; border-radius: 8px; padding: 15px;'></div>

        <script>
            const pipelineUtcTime = new Date("{current_utc_iso}");
            document.getElementById("local-timestamp").innerText = pipelineUtcTime.toLocaleString(undefined, {{
                dateStyle: "long",
                timeStyle: "short"
            }});
        </script>
    </body>
    </html>
    """

    # Save out file to disk
    with open("application_sankey.html", "w", encoding="utf-8") as file:
        file.write(html_template)

    print("\n🎉 ARCHITECTURE COMPILED SUCCESSFULLY!")
    print("-> Web asset written locally as 'application_sankey.html'")