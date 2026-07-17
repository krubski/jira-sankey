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
        'Applied', 'Applied > No Response', 'Applied > Rejected', 
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
        {"id_key": "TotalApplied",           "type": "root",   "name": f"Applied ({total_applied})",                                       "column": 1, "color": "#BDBDBD", "count": total_applied},
        
        # Column 2: Pipeline Core Progress Outcomes (Unified Green Tracks)
        {"id_key": "Applied",                "type": "status", "name": f"Applied > Pending ({status_counts.get('Applied', 0)})",           "column": 2, "color": "#2ecc71", "count": status_counts.get('Applied', 0)},
        {"id_key": "Applied > No Response",  "type": "status", "name": f"Applied > No Response ({status_counts.get('Applied > No Response', 0)})", "column": 2, "color": "#f1c40f", "count": status_counts.get('Applied > No Response', 0)},
        {"id_key": "Applied > Rejected",     "type": "status", "name": f"Applied > Rejected ({status_counts.get('Applied > Rejected', 0)})",  "column": 2, "color": "#e74c3c", "count": status_counts.get('Applied > Rejected', 0)},
        {"id_key": "Screened",               "type": "status", "name": f"Screened ({combined_screened})",                                  "column": 2, "color": "#2ecc71", "count": combined_screened},
        
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
        'Applied': f"Applied > Pending ({status_counts.get('Applied', 0)})",
        'Applied > No Response': f"Applied > No Response ({status_counts.get('Applied > No Response', 0)})",
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
            if status in status_to_node and status in active_keys:
                dest_node = status_to_node[status]
                links_raw.append({"source": root_node_name, "target": dest_node, "origin": src})

    # Group matching linkages and map them explicitly to numeric node indices
    links_config = []
    if links_raw:
        links_df = pd.DataFrame(links_raw).groupby(['source', 'target', 'origin']).size().reset_index(name='value')
        for _, r in links_df.iterrows():
            if r['source'] in node_name_to_idx and r['target'] in node_name_to_idx:
                links_config.append({
                    "source": node_name_to_idx[r['source']],
                    "target": node_name_to_idx[r['target']],
                    "value": int(r['value']),
                    "origin_source": r['origin']
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
    print("\n5. Compiling HTML template data...")
    html_template = f"""<!DOCTYPE html>
    <html>
    <head>
        <title>Jira Application Source Pipeline (D3.js)</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <!-- Inline Data URI SVG Favicon pulling from the 🥇 Unicode point -->
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>{favicon_emoji}</text></svg>">
        <script src="https://d3js.org/d3.v7.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12.3/dist/d3-sankey.min.js"></script>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f6f9; padding: 10px; margin: 0; display: flex; flex-direction: column; align-items: center; }}
            .container {{ width: 100%; max-width: 1250px; background: white; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); padding: 15px; box-sizing: border-box; position: relative; }}
            .header {{ text-align: left; margin-bottom: 25px; }}
            .header h2 {{ color: #2c3e50; margin: 0 0 5px 0; font-size: 1.5rem; }}
            .header p {{ color: #7f8c8d; margin: 0; font-size: 13px; }}
            .svg-wrapper {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }}
            #sankey_svg {{ width: 100%; height: auto; min-width: 850px; }}
            .node rect {{ fill-opacity: 0.95; shape-rendering: geometricPrecision; stroke: #ffffff; stroke-width: 2px; cursor: pointer; }}
            .node rect:hover {{ filter: brightness(1.05); }}
            .node text {{ font-size: 11px; font-weight: bold; fill: #2c3e50; pointer-events: none; }}
            .link {{ fill: none; stroke-opacity: 0.28; transition: stroke-opacity 0.2s, opacity 0.2s, stroke-width 0.2s; }}
            .link:hover {{ stroke-opacity: 0.6 !important; }}
            #tooltip {{ position: absolute; padding: 8px 12px; background: rgba(44, 62, 80, 0.95); color: white; border-radius: 4px; font-size: 12px; pointer-events: none; opacity: 0; transition: opacity 0.15s ease; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.2); z-index: 100; }}
            #cohort-hud {{ position: relative; top: 0; right: 0; background: #2c3e50; color: white; padding: 15px; border-radius: 6px; box-shadow: 0 4px 10px rgba(0,0,0,0.15); font-size: 12px; display: none; width: 100%; box-sizing: border-box; line-height: 1.5; margin-bottom: 15px; }}
            #cohort-hud h4 {{ margin: 0 0 8px 0; color: #2ecc71; border-bottom: 1px solid rgba(255,255,255,0.2); padding-bottom: 4px; font-size: 13px; }}
            #cohort-hud ul {{ margin: 0; padding-left: 18px; }}
            @media (min-width: 768px) {{ body {{ padding: 30px; }} .container {{ padding: 25px; }} .header h2 {{ font-size: 1.8rem; }} #cohort-hud {{ position: absolute; top: 25px; right: 25px; width: 280px; margin-bottom: 0; }} .node text {{ font-size: 12px; }} }}
            .faded {{ opacity: 0.04 !important; }}
            .highlighted-link {{ stroke-opacity: 0.8 !important; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Jira Application Source Pipeline</h2>
                <p>Interactive 4-Column Pipeline built natively with <strong>D3.js</strong>.</p>
                <p>Last Synchronized: <span id="local-timestamp">Calculating...</span></p>
            </div>
            <div id="cohort-hud"></div>
            <div class="svg-wrapper">
                <svg id="sankey_svg" viewBox="0 0 1200 550" preserveAspectRatio="xMinYMin meet"></svg>
            </div>
        </div>
        <div id="tooltip"></div>
        <script>
            const graphData = {d3_data_json};
            graphData.links.forEach(l => {{ l.originalWidth = l.width; }});
            
            const svg = d3.select("#sankey_svg"), width = 1200, height = 550;
            svg.on("click", function(event) {{ if (event.target.tagName === "svg") resetSankeyEffects(); }});
            
            function resetSankeyEffects() {{ 
                linkElements.classed("faded", false).classed("highlighted-link", false).style("stroke-width", d => Math.max(1.5, d.originalWidth)); 
                nodeElements.classed("faded", false); 
                d3.select("#cohort-hud").style("display", "none"); 
                isHighlighted = false; 
            }}
            
            const sankey = d3.sankey().nodeWidth(22).nodePadding(32).extent([[10, 10], [width - 180, height - 10]]);
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
            
            const linkElements = svg.append("g").attr("fill", "none").selectAll("path").data(graph.links).enter().append("path").attr("class", "link").attr("d", d3.sankeyLinkHorizontal()).attr("stroke", (d, i) => `url(#grad-${{i}})`).style("stroke-width", d => Math.max(1.5, d.width)).attr("data-origin-source", d => d.origin_source);
            const nodeElements = svg.append("g").selectAll("g").data(graph.nodes).enter().append("g").attr("class", "node").attr("transform", d => `translate(${{d.x0}},${{d.y0}})`);
            
            let isHighlighted = false;
            nodeElements.append("rect").attr("height", d => Math.max(4, d.y1 - d.y0)).attr("width", d => d.x1 - d.x0).attr("rx", 5).attr("ry", 5).style("fill", d => d.color).on("click", function(event, clickedNode) {{
                event.stopPropagation();
                const activeNodes = new Set(), activeLinks = new Set(); activeNodes.add(clickedNode.index);
                graph.links.forEach(l => l.currentScaledValue = undefined);
                
                if (clickedNode.column === 0) {{
                    let platformFilter = clickedNode.name.split(" (")[0], downstreamStatuses = {{}};
                    linkElements.each(function(l) {{ if (l.origin_source === platformFilter) {{ activeLinks.add(l); activeNodes.add(l.source.index); activeNodes.add(l.target.index); if (l.target.column >= 2) {{ let sName = l.target.name.split(" (")[0]; if (sName === "Screened" && l.target.column === 2) return; downstreamStatuses[sName] = (downstreamStatuses[sName] || 0) + l.value; }} }} }});
                    let hudHtml = `<h4>${{platformFilter}} Status Breakdown</h4><ul>`;
                    Object.keys(downstreamStatuses).sort((a,b) => downstreamStatuses[b] - downstreamStatuses[a]).forEach(s => {{ hudHtml += `<li><strong>${{s}}</strong>: ${{downstreamStatuses[s]}} application(s)</li>`; }});
                    d3.select("#cohort-hud").html(hudHtml).style("display", "block");
                }} else if (clickedNode.column === 1) {{
                    linkElements.each(function(l) {{ activeLinks.add(l); activeNodes.add(l.source.index); activeNodes.add(l.target.index); }});
                }} else {{
                    let exactSlices = {{}}, targetLinksToEvaluate = [];
                    clickedNode.targetLinks.forEach(l => {{ targetLinksToEvaluate.push(l); }});
                    targetLinksToEvaluate.forEach(link => {{ exactSlices[link.origin_source] = (exactSlices[link.origin_source] || 0) + link.value; }});
                    
                    linkElements.each(function(l) {{ 
                        if (exactSlices[l.origin_source] !== undefined) {{
                            // Column 0 -> 1 (Platform to Applied)
                            if (l.source.column === 0 && l.target.column === 1) {{
                                activeLinks.add(l); 
                                activeNodes.add(l.source.index);
                                activeNodes.add(l.target.index);
                                d3.select(this).style("stroke-width", Math.max(2, l.originalWidth * (exactSlices[l.origin_source] / l.value))); 
                            }} 
                            // Column 1 -> 2 (Applied to Stage 2 Outcomes)
                            else if (l.source.column === 1 && l.target.column === 2) {{
                                // Direct match if we clicked a Column 2 outcome node
                                if (clickedNode.column === 2 && l.target.index === clickedNode.index) {{
                                    activeLinks.add(l);
                                    activeNodes.add(l.source.index);
                                    activeNodes.add(l.target.index);
                                }} 
                                // Route back through the Screened node if we clicked deep in Column 3
                                else if (clickedNode.column === 3 && l.target.name.startsWith("Screened")) {{
                                    activeLinks.add(l);
                                    activeNodes.add(l.source.index);
                                    activeNodes.add(l.target.index);
                                }}
                            }}
                            // Column 2 -> 3 (Screened to Deep Stages)
                            else if (l.source.column === 2 && l.target.column === 3 && l.target.index === clickedNode.index) {{
                                activeLinks.add(l);
                                activeNodes.add(l.source.index);
                                activeNodes.add(l.target.index);
                            }}
                        }} 
                    }});
                    
                    let hudHtml = `<h4>${{clickedNode.name.split(" (")[0]}} Source Cohorts</h4><ul>`;
                    Object.keys(exactSlices).sort((a,b) => exactSlices[b] - exactSlices[a]).forEach(p => {{ hudHtml += `<li><strong>${{p}}</strong>: ${{exactSlices[p]}} application(s)</li>`; }});
                    d3.select("#cohort-hud").html(hudHtml).style("display", "block");
                }}
                linkElements.classed("faded", l => !activeLinks.has(l)).classed("highlighted-link", l => activeLinks.has(l));
                nodeElements.classed("faded", n => !activeNodes.has(n.index)); isHighlighted = true;
            }});
            
            nodeElements.append("text").attr("x", d => d.x1 - d.x0 + 12).attr("y", d => (d.y1 - d.y0) / 2).attr("dy", "0.35em").text(d => d.name);
            document.getElementById("local-timestamp").innerText = new Date("{current_utc_iso}").toLocaleString();
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