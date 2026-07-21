import os
import json
import requests
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

# ==========================================
# 1. INITIALIZATION & ENVIRONMENT SETUP
# ==========================================
print("1. Initializing script and loading environment...")
load_dotenv()  # Automatically load local .env file variables

current_utc_iso = datetime.now(timezone.utc).isoformat()

JIRA_URL = os.environ.get('JIRA_URL')
JIRA_EMAIL = os.environ.get('JIRA_EMAIL')
JIRA_TOKEN = os.environ.get('JIRA_TOKEN') 
JIRA_FILTER_ID = os.environ.get('JIRA_FILTER_ID')

print(f"   -> JIRA_URL: {JIRA_URL}")
print(f"   -> JIRA_EMAIL: {JIRA_EMAIL}")
print(f"   -> JIRA_FILTER_ID: {JIRA_FILTER_ID}")
print("   -> JIRA_TOKEN is " + ("present." if JIRA_TOKEN else "MISSING!"))

# Format base endpoint cleanly regardless of environment protocol string
if JIRA_URL and JIRA_URL.startswith('http'):
    clean_domain = JIRA_URL.replace('https://', '').replace('http://', '').split('/')[0]
    api_url = f'https://{clean_domain}/rest/api/3/search/jql'
else:
    api_url = f'https://{JIRA_URL}/rest/api/3/search/jql'

# Define Unicode token for the 🥇 (Gold Medal) emoji to keep f-string building simple
favicon_emoji = "\U0001F947"


# ==========================================
# 2. JIRA API EXTRACTION LOOP
# ==========================================
print("\n2. Connecting to Jira API...")
all_issues = []
next_page_token = None
max_results = 100

headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
auth = (JIRA_EMAIL, JIRA_TOKEN)

while True:
    payload = {
        'jql': f'filter = {JIRA_FILTER_ID}',
        'maxResults': max_results,
        'fields': [
            'summary', 'status', 'assignee', 
            'customfield_10040', 'customfield_10041', 'customfield_10042'
        ],
    }
    if next_page_token:
        payload['nextPageToken'] = next_page_token

    try:
        response = requests.post(api_url, data=json.dumps(payload), headers=headers, auth=auth)
        if response.status_code != 200:
            print(f'   -> Error Payload Response: {response.text}')
            break

        data = response.json()
        batch = data.get('issues', [])
        if not batch:
            print("   -> Received empty batch of issues. Breaking loop.")
            break

        all_issues.extend(batch)
        print(f'   -> Retrieved {len(all_issues)} issues so far...')
        
        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break
            
    except Exception as e:
        print(f"   -> Network/Request Exception occurred: {str(e)}")
        break


# ==========================================
# 3. DATA CLEANING & REFORMATTING
# ==========================================
print(f"\n3. Processing Data (Total Issues Downloaded: {len(all_issues)})...")

if all_issues:
    df = pd.json_normalize(all_issues)

    columns_to_keep = {
        'key': 'Issue Key',
        'fields.summary': 'Summary',
        'fields.status.name': 'Status',
        'fields.assignee.displayName': 'Assignee',
        'fields.customfield_10040': 'Job Title',
        'fields.customfield_10041': 'Company',
        'fields.customfield_10042.value': 'Source',
    }

    # Filter and rename incoming payload columns safely
    existing_columns = [col for col in columns_to_keep.keys() if col in df.columns]
    df_clean = df[existing_columns].rename(columns=columns_to_keep)

    if 'Issue Key' in df_clean.columns:
        df_clean = df_clean.set_index('Issue Key')

    desired_order = ['Summary', 'Status', 'Assignee', 'Job Title', 'Company', 'Source']
    df_clean = df_clean.reindex(columns=desired_order).fillna("Unknown")

    df_clean['Source'] = df_clean['Source'].astype(str)
    df_clean['Status'] = df_clean['Status'].astype(str)

    # Standardize string formatting for specific hiring channels
    def clean_source_casing(src):
        mapping = {
            'linkedin': 'LinkedIn', 'builtin': 'Builtin', 
            'networking': 'Networking', 'indeed': 'Indeed', 
            'dad': 'Dad', 'scoutify': 'Scoutify'
        }
        return mapping.get(src.lower(), src)

    df_clean['Source'] = df_clean['Source'].apply(clean_source_casing)

    # Target functional stages matching visualization template requirements
    valid_statuses = [
        'Applied', 'Applied > Pending', 'Applied > No Response', 'Applied > Position on Hold', 'Applied > Rejected', 
        'Screened', 'Screened > Pending', 'Screened > No Response', 'Screened > Rejected'
    ]
    
    print("\n4. Filtering Status Distribution Counts...")
    print("   -> Unique statuses found in your raw Jira data:")
    print(df_clean['Status'].value_counts())
    
    df_filtered = df_clean[df_clean['Status'].isin(valid_statuses)]
    print(f"   -> Count after matching against valid pipeline statuses: {len(df_filtered)}")


    # ==========================================
    # 4. SANKEY PIPELINE COUNTS & NODE GENERATION
    # ==========================================
    total_applied = len(df_filtered)
    source_counts = df_filtered['Source'].value_counts().to_dict()
    status_counts = df_filtered['Status'].value_counts().to_dict()

    # Consolidate 'Applied' and 'Applied > Pending' into one count for the node
    applied_pending_count = status_counts.get('Applied', 0) + status_counts.get('Applied > Pending', 0)

    # Consolidate deep stages back into their respective high-level categories
    combined_screened = sum(status_counts.get(st, 0) for st in ['Screened', 'Screened > Pending', 'Screened > No Response', 'Screened > Rejected'])

    raw_nodes_config = [
        # Column 0: Sourcing Channels
        {"id_key": "Builtin",                "type": "source", "name": f"Builtin ({source_counts.get('Builtin', 0)})",                     "column": 0, "color": "#07006c", "count": source_counts.get('Builtin', 0)},
        {"id_key": "Dad",                    "type": "source", "name": f"Dad ({source_counts.get('Dad', 0)})",                             "column": 0, "color": "#d4af37", "count": source_counts.get('Dad', 0)},
        {"id_key": "Indeed",                 "type": "source", "name": f"Indeed ({source_counts.get('Indeed', 0)})",                       "column": 0, "color": "#2164f3", "count": source_counts.get('Indeed', 0)},
        {"id_key": "JobLeads",               "type": "source", "name": f"JobLeads ({source_counts.get('JobLeads', 0)})",                     "column": 0, "color": "#eb6c65", "count": source_counts.get('JobLeads', 0)},
        {"id_key": "LinkedIn",               "type": "source", "name": f"LinkedIn ({source_counts.get('LinkedIn', 0)})",                   "column": 0, "color": "#0072b1", "count": source_counts.get('LinkedIn', 0)},
        {"id_key": "Me",                     "type": "source", "name": f"Me ({source_counts.get('Me', 0)})",                               "column": 0, "color": "#27a6f5", "count": source_counts.get('Me', 0)},
        {"id_key": "Networking",             "type": "source", "name": f"Networking ({source_counts.get('Networking', 0)})",               "column": 0, "color": "#fa9214", "count": source_counts.get('Networking', 0)},
        {"id_key": "Scoutify",               "type": "source", "name": f"Scoutify ({source_counts.get('Scoutify', 0)})",                   "column": 0, "color": "#7bcd9d", "count": source_counts.get('Scoutify', 0)},
        {"id_key": "Simplify",               "type": "source", "name": f"Simplify ({source_counts.get('Simplify', 0)})",                   "column": 0, "color": "#3bc4d7", "count": source_counts.get('Simplify', 0)},
        
        # Column 1: Master Central Aggregation node
        {"id_key": "TotalApplied",           "type": "root",   "name": f"Applied ({total_applied})",                                       "column": 1, "color": "#64748b", "count": total_applied},
        
        # Column 2: Pipeline Core Progress Outcomes
        {"id_key": "Applied > Pending",         "type": "status", "name": f"Applied > Pending ({applied_pending_count})",                       "column": 2, "color": "#2ecc71", "count": applied_pending_count},
        {"id_key": "Applied > No Response",     "type": "status", "name": f"Applied > No Response ({status_counts.get('Applied > No Response', 0)})",   "column": 2, "color": "#f1c40f", "count": status_counts.get('Applied > No Response', 0)},
        {"id_key": "Applied > Position on Hold", "type": "status", "name": f"Applied > Position on Hold ({status_counts.get('Applied > Position on Hold', 0)})", "column": 2, "color": "#7f8c8d", "count": status_counts.get('Applied > Position on Hold', 0)},
        {"id_key": "Applied > Rejected",        "type": "status", "name": f"Applied > Rejected ({status_counts.get('Applied > Rejected', 0)})",        "column": 2, "color": "#e74c3c", "count": status_counts.get('Applied > Rejected', 0)},
        {"id_key": "Screened",                  "type": "status", "name": f"Screened ({combined_screened})",                                            "column": 2, "color": "#2ecc71", "count": combined_screened},
        
        # Column 3: Dedicated Deep Stages (Interview specifics)
        {"id_key": "Screened > Pending",     "type": "status", "name": f"Screened > Pending ({status_counts.get('Screened > Pending', 0)})",     "column": 3, "color": "#2ecc71", "count": status_counts.get('Screened > Pending', 0)},
        {"id_key": "Screened > No Response", "type": "status", "name": f"Screened > No Response ({status_counts.get('Screened > No Response', 0)})", "column": 3, "color": "#f1c40f", "count": status_counts.get('Screened > No Response', 0)},
        {"id_key": "Screened > Rejected",    "type": "status", "name": f"Screened > Rejected ({status_counts.get('Screened > Rejected', 0)})",   "column": 3, "color": "#e74c3c", "count": status_counts.get('Screened > Rejected', 0)}
    ]

    # Filter out empty nodes to prevent orphan text blocks from appearing on the graph canvas
    nodes_config = [node for node in raw_nodes_config if node["count"] > 0]
    active_keys = {n["id_key"] for n in nodes_config}
    node_name_to_idx = {n["name"]: i for i, n in enumerate(nodes_config)}
    
    root_node_name = f"Applied ({total_applied})"
    source_to_node = {src: f"{src} ({source_counts.get(src, 0)})" for src in source_counts.keys()}
    shared_screened_label = f"Screened ({combined_screened})"
    
    status_to_node = {
        'Applied': f"Applied > Pending ({applied_pending_count})",
        'Applied > Pending': f"Applied > Pending ({applied_pending_count})",
        'Applied > No Response': f"Applied > No Response ({status_counts.get('Applied > No Response', 0)})",
        'Applied > Position on Hold': f"Applied > Position on Hold ({status_counts.get('Applied > Position on Hold', 0)})",
        'Applied > Rejected': f"Applied > Rejected ({status_counts.get('Applied > Rejected', 0)})",
        'Screened': shared_screened_label,
        'Screened > Pending': shared_screened_label,
        'Screened > No Response': shared_screened_label,
        'Screened > Rejected': shared_screened_label
    }


    # ==========================================
    # 5. HIGH-ACCURACY DATA LINK ROUTING LOOP
    # ==========================================
    links_raw = []

    for _, row in df_clean.iterrows():
        src = row['Source']
        status = row['Status']
        
        # Check node validity before mapping path records
        if status not in valid_statuses or src not in source_to_node:
            continue
        if src not in active_keys or "TotalApplied" not in active_keys:
            continue

        src_node = source_to_node[src]
        
        # Rule 1: Every application links first from its Platform -> Consolidated Root Node
        links_raw.append({"source": src_node, "target": root_node_name, "origin": src})

        # Rule 2: Multi-stage mapping routing paths out from Consolidated Root
        if status.startswith('Screened >'):
            links_raw.append({"source": root_node_name, "target": shared_screened_label, "origin": src})
            
            # Sub-allocation into deep 4th column endpoints
            if status == 'Screened > Pending':
                col4_name = f"Screened > Pending ({status_counts.get('Screened > Pending', 0)})"
            elif status == 'Screened > No Response':
                col4_name = f"Screened > No Response ({status_counts.get('Screened > No Response', 0)})"
            else:
                col4_name = f"Screened > Rejected ({status_counts.get('Screened > Rejected', 0)})"
                
            links_raw.append({"source": shared_screened_label, "target": col4_name, "origin": src})
            
        elif status == 'Screened':
            links_raw.append({"source": root_node_name, "target": shared_screened_label, "origin": src})
            
        else:
            # Direct single-link mapping from Root to Column 2 target
            dest_node = status_to_node.get(status)
            if dest_node and dest_node in node_name_to_idx:
                links_raw.append({"source": root_node_name, "target": dest_node, "origin": src})

    # Group matching linkages into SINGLE links per path, but keep origin breakdown metadata for the HUD
    links_config = []
    if links_raw:
        links_df = pd.DataFrame(links_raw)
        grouped = links_df.groupby(['source', 'target'])
        for (src_name, tgt_name), group in grouped:
            if src_name in node_name_to_idx and tgt_name in node_name_to_idx:
                origin_counts = group['origin'].value_counts().to_dict()
                links_config.append({
                    "source": node_name_to_idx[src_name],
                    "target": node_name_to_idx[tgt_name],
                    "value": len(group),
                    "origins": origin_counts
                })

    # Clean temporary calculation fields to form raw compliance D3 payload structures
    for n in nodes_config:
        n.pop("id_key", None)
        n.pop("type", None)
        n.pop("count", None)

    d3_data_json = json.dumps({"nodes": nodes_config, "links": links_config})


    # ==========================================
    # 6. D3.JS RUNTIME HTML TEMPLATE GENERATION
    # ==========================================
    print("\n5. Compiling HTML template data with Unified Light/Dark Theme variables...")
    html_template = f"""<!DOCTYPE html>
    <html>
    <head>
        <title>Jira Application Source Pipeline (D3.js)</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <!-- Google Fonts: Space Grotesk (Title & KPI Numerics) + Fira Code (Monospace Labels) -->
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
        <!-- Inline Data URI SVG Favicon pulling from the 🥇 Unicode point -->
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>{favicon_emoji}</text></svg>">
        <script src="https://d3js.org/d3.v7.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12.3/dist/d3-sankey.min.js"></script>
        <style>
            /* Theming Variables (Default: Dark Mode) */
            :root {{
                --bg-body: #0f172a;
                --container-bg: #1e293b;
                --container-border: #334155;
                --text-main: #f8fafc;
                --text-sub: #94a3b8;
                --timestamp-bg: #0f172a;
                --timestamp-border: #334155;
                --timestamp-color: #38bdf8;
                
                /* Unified Dark HUD & Card Theme */
                --panel-bg: #111827;
                --panel-border: #374151;
                --panel-label: #9ca3af;
                --card-bg: #1f2937;
                --card-border: #374151;
                --card-title: #9ca3af;
                --card-val: #f9fafb;
                
                --node-text: #cbd5e1;
                --toggle-track-bg: #334155;
                --toggle-knob-bg: #1e293b;
                --toggle-text-inactive: #94a3b8;
                --toggle-text-active: #f8fafc;
                --toggle-border: #475569;
            }}

            /* Light Mode Theme Overrides */
            [data-theme="light"] {{
                --bg-body: #f8fafc;
                --container-bg: #ffffff;
                --container-border: #e2e8f0;
                --text-main: #0f172a;
                --text-sub: #64748b;
                --timestamp-bg: #f1f5f9;
                --timestamp-border: #e2e8f0;
                --timestamp-color: #0284c7;
                
                /* Unified Light HUD & Card Theme */
                --panel-bg: #f8fafc;
                --panel-border: #cbd5e1;
                --panel-label: #475569;
                --card-bg: #ffffff;
                --card-border: #cbd5e1;
                --card-title: #475569;
                --card-val: #0f172a;
                
                --node-text: #334155;
                --toggle-track-bg: #e2e8f0;
                --toggle-knob-bg: #ffffff;
                --toggle-text-inactive: #64748b;
                --toggle-text-active: #0f172a;
                --toggle-border: #cbd5e1;
            }}

            body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: var(--bg-body); color: var(--text-main); padding: 15px; margin: 0; display: flex; flex-direction: column; align-items: center; transition: background-color 0.3s ease; }}
            .container {{ width: 100%; max-width: 1280px; background: var(--container-bg); border: 1px solid var(--container-border); border-radius: 12px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.15); padding: 20px; box-sizing: border-box; position: relative; transition: background-color 0.3s ease, border-color 0.3s ease; }}
            
            /* Header Styling */
            .header-layout {{ display: flex; flex-direction: column; gap: 20px; margin-bottom: 25px; position: relative; }}
            @media (min-width: 850px) {{
                .header-layout {{ display: grid; grid-template-columns: 1fr 340px; align-items: start; }}
            }}

            .title-area h2 {{ 
                font-family: 'Space Grotesk', sans-serif;
                color: var(--text-main); 
                margin: 0 0 6px 0; 
                font-size: 1.85rem; 
                font-weight: 700;
                letter-spacing: -0.03em;
                display: flex;
                align-items: center;
                gap: 12px;
                flex-wrap: wrap;
            }}
            .title-area p {{ 
                color: var(--text-sub); 
                margin: 0 0 8px 0; 
                font-size: 13.5px; 
                line-height: 1.5;
            }}
            .title-area #local-timestamp {{
                font-family: 'Fira Code', monospace;
                font-size: 11px;
                background: var(--timestamp-bg);
                border: 1px solid var(--timestamp-border);
                padding: 3px 10px;
                border-radius: 12px;
                color: var(--timestamp-color);
                font-weight: 500;
            }}

            /* Modern Segmented Toggle Switch to the right of 'pipeline' in header */
            .theme-switch {{
                display: inline-flex;
                align-items: center;
                background: var(--toggle-track-bg);
                border: 1px solid var(--toggle-border);
                border-radius: 20px;
                padding: 2px;
                cursor: pointer;
                user-select: none;
                vertical-align: middle;
                margin-left: 8px;
                box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
                transition: background-color 0.3s ease, border-color 0.3s ease;
            }}
            .theme-option {{
                font-family: 'Fira Code', monospace;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
                border-radius: 16px;
                display: inline-flex;
                align-items: center;
                gap: 4px;
                color: var(--toggle-text-inactive);
                transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            }}
            .theme-switch[data-active="light"] .light-opt,
            .theme-switch[data-active="dark"] .dark-opt {{
                background: var(--toggle-knob-bg);
                color: var(--toggle-text-active);
                box-shadow: 0 2px 5px rgba(0,0,0,0.15);
            }}

            /* Unified KPI Panel Styling */
            .kpi-panel {{
                background: var(--panel-bg);
                border: 1px solid var(--panel-border);
                border-radius: 12px;
                padding: 14px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                transition: background-color 0.3s ease, border-color 0.3s ease;
            }}
            .kpi-badge-row {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 12px;
            }}
            .kpi-label {{
                font-family: 'Fira Code', monospace;
                font-size: 10px;
                text-transform: uppercase;
                letter-spacing: 0.8px;
                color: var(--panel-label);
                font-weight: 700;
            }}
            .kpi-focus-badge {{
                font-family: 'Space Grotesk', sans-serif;
                font-size: 11px;
                font-weight: 700;
                padding: 3px 10px;
                border-radius: 20px;
                transition: all 0.3s ease;
            }}

            /* 2x2 Stat Grid */
            .kpi-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 8px;
            }}
            .kpi-card {{
                background: var(--card-bg);
                border: 1px solid var(--card-border);
                border-radius: 8px;
                padding: 8px 10px;
                transition: background-color 0.3s ease, border-color 0.3s ease;
            }}
            .kpi-card .card-title {{
                font-family: 'Fira Code', monospace;
                font-size: 9.5px;
                text-transform: uppercase;
                color: var(--card-title);
                font-weight: 600;
                letter-spacing: 0.5px;
            }}
            .kpi-card .card-val {{
                font-family: 'Space Grotesk', sans-serif;
                font-size: 1.35rem;
                font-weight: 700;
                margin-top: 2px;
                line-height: 1.1;
                color: var(--card-val);
            }}

            /* SVG Canvas Wrapper */
            .svg-wrapper {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }}
            #sankey_svg {{ width: 100%; height: auto; min-width: 850px; }}
            .node rect {{ fill-opacity: 0.95; shape-rendering: geometricPrecision; stroke: var(--container-bg); stroke-width: 2px; cursor: pointer; }}
            .node rect:hover {{ filter: brightness(1.15); }}
            .node text {{ font-size: 11.5px; font-weight: 600; fill: var(--node-text); pointer-events: none; }}
            .link {{ fill: none; stroke-opacity: 0.4; transition: stroke-opacity 0.2s, opacity 0.2s, stroke-width 0.2s; }}
            .link:hover {{ stroke-opacity: 0.8 !important; }}
            #tooltip {{ position: absolute; padding: 8px 12px; background: rgba(15, 23, 42, 0.95); border: 1px solid #334155; color: white; border-radius: 6px; font-size: 12px; pointer-events: none; opacity: 0; transition: opacity 0.15s ease; font-weight: bold; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 100; }}
            
            /* Unified Cohort HUD Detail Card (Positioned Below Chart) */
            #cohort-hud {{ 
                position: relative; 
                background: var(--panel-bg); 
                border: 1px solid var(--panel-border); 
                box-shadow: 0 6px 20px rgba(0, 0, 0, 0.1);
                color: var(--text-main); 
                padding: 18px; 
                border-radius: 12px; 
                font-size: 13px; 
                display: none; 
                width: 100%; 
                box-sizing: border-box; 
                line-height: 1.5; 
                margin-top: 16px; 
                animation: fadeIn 0.2s ease-in-out;
                transition: background-color 0.3s ease, border-color 0.3s ease;
            }}

            @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(-4px); }}
                to   {{ opacity: 1; transform: translateY(0); }}
            }}

            #cohort-hud h4 {{ margin: 0 0 10px 0; color: #0284c7; border-bottom: 1px solid var(--panel-border); padding-bottom: 6px; font-size: 14px; font-weight: 700; font-family: 'Space Grotesk', sans-serif; }}
            #cohort-hud ul {{ margin: 0; padding-left: 18px; color: var(--text-sub); }}
            #cohort-hud ul li {{ margin-bottom: 3px; }}
            .faded {{ opacity: 0.05 !important; }}
            .highlighted-link {{ stroke-opacity: 0.85 !important; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header-layout">
                <!-- Title & Meta Header -->
                <div class="title-area">
                    <h2>
                        Jira Application Source Pipeline
                        <!-- Segmented Theme Toggle Switch to the right of 'pipeline' -->
                        <div class="theme-switch" id="theme-switch" data-active="dark" onclick="toggleTheme()">
                            <span class="theme-option light-opt">☀️ Light</span>
                            <span class="theme-option dark-opt">🌙 Dark</span>
                        </div>
                    </h2>
                    <p>Interactive 4-Column Pipeline built natively with <strong>D3.js</strong>.</p>
                    <p>Last Synchronized: <span id="local-timestamp">Calculating...</span></p>
                </div>

                <!-- Dynamic KPI Summary Card Panel -->
                <div class="kpi-panel">
                    <div class="kpi-badge-row">
                        <span class="kpi-label">Selected Focus</span>
                        <span id="focus-badge" class="kpi-focus-badge" style="background-color: rgba(2, 132, 199, 0.15); color: #0284c7; border: 1px solid rgba(2, 132, 199, 0.4); box-shadow: 0 0 10px rgba(2, 132, 199, 0.15);">
                            Global Pipeline
                        </span>
                    </div>
                    <div class="kpi-grid">
                        <div class="kpi-card">
                            <div class="card-title">Total Apps</div>
                            <div id="kpi-total" class="card-val">0</div>
                        </div>
                        <div class="kpi-card">
                            <div class="card-title">Active / Pending</div>
                            <div id="kpi-active" class="card-val" style="color: #0284c7;">0</div>
                        </div>
                        <div class="kpi-card">
                            <div class="card-title">Screened Rate</div>
                            <div id="kpi-screened-rate" class="card-val" style="color: #10b981;">0.0%</div>
                        </div>
                        <div class="kpi-card">
                            <div class="card-title">Rejection Rate</div>
                            <div id="kpi-rejection-rate" class="card-val" style="color: #ef4444;">0.0%</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- SVG Chart Wrapper -->
            <div class="svg-wrapper">
                <svg id="sankey_svg" viewBox="0 0 1200 650" preserveAspectRatio="xMinYMin meet"></svg>
            </div>

            <!-- Cohort HUD Detail Card (Rendered BELOW the Chart) -->
            <div id="cohort-hud"></div>
        </div>
        <div id="tooltip"></div>

        <script>
            // Theme Toggle Logic
            function setTheme(theme) {{
                const body = document.body;
                const switchEl = document.getElementById("theme-switch");
                
                if (theme === "light") {{
                    body.setAttribute("data-theme", "light");
                    switchEl.setAttribute("data-active", "light");
                    localStorage.setItem("theme", "light");
                }} else {{
                    body.removeAttribute("data-theme");
                    switchEl.setAttribute("data-active", "dark");
                    localStorage.setItem("theme", "dark");
                }}
            }}

            function toggleTheme() {{
                const currentTheme = document.body.getAttribute("data-theme");
                setTheme(currentTheme === "light" ? "dark" : "light");
            }}

            // Check saved preference on load
            (function() {{
                const savedTheme = localStorage.getItem("theme");
                if (savedTheme === "light") {{
                    setTheme("light");
                }} else {{
                    setTheme("dark");
                }}
            }})();

            const graphData = {d3_data_json};
            graphData.links.forEach(l => {{ l.originalWidth = l.width; }});
            
            const svg = d3.select("#sankey_svg"), width = 1200, height = 650;
            svg.on("click", function(event) {{ if (event.target.tagName === "svg") resetSankeyEffects(); }});
            
            // Baseline metrics setup for global dashboard
            const globalTotalApps = {total_applied};
            const globalActive = {status_counts.get('Applied', 0) + status_counts.get('Applied > Pending', 0) + status_counts.get('Screened > Pending', 0)};
            const globalScreened = {combined_screened};
            const globalRejected = {status_counts.get('Applied > Rejected', 0) + status_counts.get('Screened > Rejected', 0)};

            function updateKPIPanel(name, color, total, active, screened, rejected) {{
                const badge = d3.select("#focus-badge");
                badge.text(name)
                     .style("background-color", color + "25")
                     .style("color", color)
                     .style("border", "1px solid " + color + "60")
                     .style("box-shadow", "0 0 10px " + color + "30");

                d3.select("#kpi-total").text(total);
                d3.select("#kpi-active").text(active);
                
                const screenRate = total > 0 ? ((screened / total) * 100).toFixed(1) : "0.0";
                const rejRate = total > 0 ? ((rejected / total) * 100).toFixed(1) : "0.0";

                d3.select("#kpi-screened-rate").text(screenRate + "%");
                d3.select("#kpi-rejection-rate").text(rejRate + "%");
            }}

            function resetSankeyEffects() {{ 
                linkElements.classed("faded", false).classed("highlighted-link", false).style("stroke-width", d => Math.max(1.5, d.originalWidth)); 
                nodeElements.classed("faded", false); 
                d3.select("#cohort-hud").style("display", "none"); 
                isHighlighted = false; 

                // Reset KPI Panel back to global totals
                updateKPIPanel("Global Pipeline", "#0284c7", globalTotalApps, globalActive, globalScreened, globalRejected);
            }}
            
            const sankey = d3.sankey().nodeWidth(22).nodePadding(20).extent([[10, 10], [width - 180, height - 10]]);
            let graph = sankey(graphData);
            
            const totalCols = 4, colWidth = (width - 220) / (totalCols - 1);
            graph.nodes.forEach(node => {{ node.x0 = node.column * colWidth; node.x1 = node.x0 + sankey.nodeWidth(); }});
            sankey.update(graph);
            
            const tooltip = d3.select("#tooltip");
            const defs = svg.append("defs");
            
            graph.links.forEach((link, i) => {{
                const gradientId = `grad-${{i}}`;
                const grad = defs.append("linearGradient").attr("id", gradientId).attr("gradientUnits", "userSpaceOnUse").attr("x1", link.source.x1).attr("x2", link.target.x0);
                grad.append("stop").attr("offset", "0%").attr("stop-color", link.source.color);
                grad.append("stop").attr("offset", "100%").attr("stop-color", link.target.color);
                link.gradientId = gradientId;
            }});
            
            const linkElements = svg.append("g").attr("fill", "none").selectAll("path").data(graph.links).enter().append("path").attr("class", "link").attr("d", d3.sankeyLinkHorizontal()).attr("stroke", (d, i) => `url(#grad-${{i}})`).style("stroke-width", d => Math.max(1.5, d.width));
            const nodeElements = svg.append("g").selectAll("g").data(graph.nodes).enter().append("g").attr("class", "node").attr("transform", d => `translate(${{d.x0}},${{d.y0}})`);
            
            let isHighlighted = false;
            nodeElements.append("rect").attr("height", d => Math.max(4, d.y1 - d.y0)).attr("width", d => d.x1 - d.x0).attr("rx", 5).attr("ry", 5).style("fill", d => d.color).on("click", function(event, clickedNode) {{
                event.stopPropagation();
                const activeNodes = new Set(), activeLinks = new Set();
                activeNodes.add(clickedNode.index);

                let focusName = clickedNode.name.split(" (")[0];

                // CASE 1: Clicked a Sourcing Channel (Column 0)
                if (clickedNode.column === 0) {{
                    let platformFilter = focusName;
                    let downstreamStatuses = {{}};

                    // Trace downstream paths to harvest exact application counts by status
                    linkElements.each(function(l) {{
                        let pCount = (l.origins && l.origins[platformFilter]) || 0;
                        if (pCount > 0) {{
                            activeLinks.add(l);
                            activeNodes.add(l.source.index);
                            activeNodes.add(l.target.index);

                            let statusName = l.target.name.split(" (")[0];
                            
                            if (l.target.column === 2 && statusName !== "Screened") {{
                                downstreamStatuses[statusName] = (downstreamStatuses[statusName] || 0) + pCount;
                            }} else if (l.target.column === 3) {{
                                downstreamStatuses[statusName] = (downstreamStatuses[statusName] || 0) + pCount;
                            }}
                        }}
                    }});

                    let totalPlatformApps = Object.values(downstreamStatuses).reduce((a, b) => a + b, 0);

                    if (totalPlatformApps > 0) {{
                        let screenedCount = Object.keys(downstreamStatuses)
                            .filter(st => st.startsWith("Screened"))
                            .reduce((sum, st) => sum + downstreamStatuses[st], 0);

                        let pending = (downstreamStatuses["Applied > Pending"] || 0) + (downstreamStatuses["Screened > Pending"] || 0);
                        let noResponse = downstreamStatuses["Applied > No Response"] || 0;
                        let rejected = (downstreamStatuses["Applied > Rejected"] || 0) + (downstreamStatuses["Screened > Rejected"] || 0);

                        // Update top 2x2 KPI panel dynamically
                        updateKPIPanel(platformFilter, clickedNode.color, totalPlatformApps, pending, screenedCount, rejected);

                        let pctScreened = Math.round((screenedCount / totalPlatformApps) * 100);
                        let pctNoResp = Math.round((noResponse / totalPlatformApps) * 100);
                        let pctRej = Math.round((rejected / totalPlatformApps) * 100);
                        let pctPending = Math.max(0, 100 - (pctScreened + pctNoResp + pctRej));

                        let rawComposition = [
                            {{ key: 'pending', label: 'Pending', count: pending, pct: pctPending, color: '#0284c7' }},
                            {{ key: 'noResp',  label: 'No Resp', count: noResponse, pct: pctNoResp, color: '#d97706' }},
                            {{ key: 'rejected', label: 'Rej',     count: rejected, pct: pctRej, color: '#ef4444' }},
                            {{ key: 'screen',   label: 'Screen',  count: screenedCount, pct: pctScreened, color: '#10b981' }}
                        ];

                        let activeComposition = rawComposition.filter(d => d.count > 0 || d.pct > 0);

                        let barSegmentsHtml = activeComposition.map(d => 
                            `<div style="width: ${{d.pct}}%; background-color: ${{d.color}}; height: 100%; transition: width 0.3s ease;" title="${{d.label}}: ${{d.pct}}%"></div>`
                        ).join('');

                        let legendItemsHtml = activeComposition.map(d => 
                            `<span><span style="color:${{d.color}};">■</span> ${{d.label}} ${{d.pct}}%</span>`
                        ).join('');

                        let hudHtml = `
                            <h4>${{platformFilter}} Performance Cohort</h4>
                            <div style="margin: 6px 0 12px 0;">
                                <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--panel-label); margin-bottom: 4px;">Funnel Composition</div>
                                <div style="display: flex; height: 10px; border-radius: 5px; overflow: hidden; background: rgba(0,0,0,0.15);">
                                    ${{barSegmentsHtml}}
                                </div>
                                <div style="display: flex; gap: 10px; flex-wrap: wrap; font-size: 10px; font-weight: 600; color: var(--text-sub); margin-top: 6px;">
                                    ${{legendItemsHtml}}
                                </div>
                            </div>

                            <div style="border-top: 1px solid var(--panel-border); padding-top: 8px;">
                                <strong style="color: var(--text-main);">Detailed Breakdown:</strong>
                                <ul style="margin-top: 4px; padding-left: 16px;">
                        `;

                        Object.keys(downstreamStatuses)
                            .sort((a, b) => downstreamStatuses[b] - downstreamStatuses[a])
                            .forEach(s => {{
                                let count = downstreamStatuses[s];
                                let pct = ((count / totalPlatformApps) * 100).toFixed(1);
                                hudHtml += `<li><strong>${{s}}:</strong> ${{count}} (${{pct}}%)</li>`;
                            }});

                        hudHtml += `</ul></div>`;
                        d3.select("#cohort-hud").html(hudHtml).style("display", "block");
                    }}

                }} else if (clickedNode.column === 1) {{
                    linkElements.each(function(l) {{
                        activeLinks.add(l);
                        activeNodes.add(l.source.index);
                        activeNodes.add(l.target.index);
                    }});
                    d3.select("#cohort-hud").style("display", "none");
                    updateKPIPanel("Global Pipeline", "#0284c7", globalTotalApps, globalActive, globalScreened, globalRejected);

                }} else {{
                    let exactSlices = {{}};
                    let targetLinksToEvaluate = clickedNode.targetLinks || [];

                    targetLinksToEvaluate.forEach(l => {{
                        if (l.origins) {{
                            Object.keys(l.origins).forEach(p => {{
                                exactSlices[p] = (exactSlices[p] || 0) + l.origins[p];
                            }});
                        }}
                    }});

                    linkElements.each(function(l) {{
                        let isRelevant = false;
                        if (l.origins) {{
                            for (let p in exactSlices) {{
                                if (l.origins[p] > 0) {{
                                    if (l.source.column === 0 && l.target.column === 1) {{
                                        isRelevant = true;
                                    }} else if (l.source.column === 1 && l.target.column === 2) {{
                                        if (clickedNode.column === 2 && l.target.index === clickedNode.index) {{
                                            isRelevant = true;
                                        }} else if (clickedNode.column === 3 && l.target.name.startsWith("Screened")) {{
                                            isRelevant = true;
                                        }}
                                    }} else if (l.source.column === 2 && l.target.column === 3 && l.target.index === clickedNode.index) {{
                                        isRelevant = true;
                                    }}
                                }}
                            }}
                        }}
                        if (isRelevant) {{
                            activeLinks.add(l);
                            activeNodes.add(l.source.index);
                            activeNodes.add(l.target.index);
                        }}
                    }});

                    let totalCohortApps = Object.values(exactSlices).reduce((a, b) => a + b, 0);
                    updateKPIPanel(focusName, clickedNode.color, totalCohortApps, 0, focusName.startsWith("Screened") ? totalCohortApps : 0, focusName.includes("Rejected") ? totalCohortApps : 0);

                    let hudHtml = `<h4>${{focusName}} Source Breakdown</h4><ul>`;
                    let platformKeys = Object.keys(exactSlices).sort((a,b) => exactSlices[b] - exactSlices[a]);
                    if (platformKeys.length === 0) {{
                        hudHtml += `<li>No source cohorts found</li>`;
                    }} else {{
                        platformKeys.forEach(p => {{
                            hudHtml += `<li><strong>${{p}}</strong>: ${{exactSlices[p]}} application(s)</li>`;
                        }});
                    }}
                    hudHtml += `</ul>`;
                    d3.select("#cohort-hud").html(hudHtml).style("display", "block");
                }}

                linkElements.classed("faded", l => !activeLinks.has(l)).classed("highlighted-link", l => activeLinks.has(l));
                nodeElements.classed("faded", n => !activeNodes.has(n.index));
                isHighlighted = true;
            }});
            
            nodeElements.append("text").attr("x", d => d.x1 - d.x0 + 12).attr("y", d => (d.y1 - d.y0) / 2).attr("dy", "0.35em").text(d => d.name);
            document.getElementById("local-timestamp").innerText = new Date("{current_utc_iso}").toLocaleString();
            
            // Initialize global KPI state on load
            updateKPIPanel("Global Pipeline", "#0284c7", globalTotalApps, globalActive, globalScreened, globalRejected);
        </script>
    </body>
    </html>
    """

    # ==========================================
    # 7. ABSOLUTE DIRECTORY FILE WRITE
    # ==========================================
    print("\n6. Writing 'application_sankey.html' file locally...")
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        target_path = os.path.join(script_dir, "application_sankey.html")
        
        print(f"   -> Enforcing Absolute Write Path: {target_path}")
        
        with open(target_path, "w", encoding="utf-8") as file:
            file.write(html_template)
        print("   -> SUCCESS: File written successfully.")
        
    except Exception as e:
        print(f"   -> ERROR writing file: {str(e)}")
else:
    print("\n[!] Skipping file update because no data was retrieved from the Jira API.")