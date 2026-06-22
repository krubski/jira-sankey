import requests
import json
import pandas as pd
import os
from datetime import datetime, timezone

# Set variables
all_issues = []
next_page_token = None
max_results = 100

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

    if next_page_token:
        payload['nextPageToken'] = next_page_token

    response = requests.post(url, data=json.dumps(payload), headers=headers, auth=auth)

    if response.status_code == 200:
        data = response.json()
        batch = data.get('issues', [])
        if not batch:
            break
        all_issues.extend(batch)
        print(f'-> Retrieved {len(all_issues)} issues...')
        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break
    else:
        print(f'Error fetching data from Jira: {response.status_code}')
        break

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

    existing_columns = [col for col in columns_to_keep.keys() if col in df.columns]
    df_clean = df[existing_columns].rename(columns=columns_to_keep)

    if 'Issue Key' in df_clean.columns:
        df_clean = df_clean.set_index('Issue Key')

    desired_order = ['Summary', 'Status', 'Assignee', 'Job Title', 'Company', 'Source']
    df_clean = df_clean.reindex(columns=desired_order)

    df_clean['Source'] = df_clean['Source'].astype(str)
    df_clean['Status'] = df_clean['Status'].astype(str)

    def clean_source(src):
        src_lower = src.lower()
        if src_lower == 'linkedin': return 'LinkedIn'
        if src_lower == 'builtin': return 'Builtin'
        if src_lower == 'networking': return 'Networking'
        if src_lower == 'indeed': return 'Indeed'
        return src

    df_clean['Source'] = df_clean['Source'].apply(clean_source)

    # =========================================================================
    # CALCULATE AGGREGATES & CONSTRUCT GRAPH
    # =========================================================================
    valid_statuses = ['Applied', 'Applied > No Response', 'Applied > Rejected', 'Screened', 'Screened > No Response', 'Screened > Rejected']
    df_filtered = df_clean[df_clean['Status'].isin(valid_statuses)]

    total_applied = len(df_filtered)
    source_counts = df_filtered['Source'].value_counts().to_dict()
    status_counts = df_filtered['Status'].value_counts().to_dict()

    combined_screened = status_counts.get('Screened', 0) + status_counts.get('Screened > No Response', 0) + status_counts.get('Screened > Rejected', 0)

    raw_nodes_config = [
        # Column 0: Sourcing Channels
        {"id_key": "Builtin", "type": "source", "name": f"Builtin ({source_counts.get('Builtin', 0)})", "column": 0, "color": "#07006c", "count": source_counts.get('Builtin', 0)},
        {"id_key": "Indeed", "type": "source", "name": f"Indeed ({source_counts.get('Indeed', 0)})", "column": 0, "color": "#2164f3", "count": source_counts.get('Indeed', 0)},
        {"id_key": "LinkedIn", "type": "source", "name": f"LinkedIn ({source_counts.get('LinkedIn', 0)})", "column": 0, "color": "#0072b1", "count": source_counts.get('LinkedIn', 0)},
        {"id_key": "Me", "type": "source", "name": f"Me ({source_counts.get('Me', 0)})", "column": 0, "color": "#27a6f5", "count": source_counts.get('Me', 0)},
        {"id_key": "Networking", "type": "source", "name": f"Networking ({source_counts.get('Networking', 0)})", "column": 0, "color": "#fa9214", "count": source_counts.get('Networking', 0)},
        {"id_key": "Simplify", "type": "source", "name": f"Simplify ({source_counts.get('Simplify', 0)})", "column": 0, "color": "#3bc4d7", "count": source_counts.get('Simplify', 0)},
        
        # Column 1: Core Consolidation Point
        {"id_key": "TotalApplied", "type": "root", "name": f"Applied ({total_applied})", "column": 1, "color": "#BDBDBD", "count": total_applied},
        
        # Column 2: Outcomes
        {"id_key": "Applied", "type": "status", "name": f"Active / In Review ({status_counts.get('Applied', 0)})", "column": 2, "color": "#2ecc71", "count": status_counts.get('Applied', 0)},
        {"id_key": "Applied > No Response", "type": "status", "name": f"Applied > No Response ({status_counts.get('Applied > No Response', 0)})", "column": 2, "color": "#f1c40f", "count": status_counts.get('Applied > No Response', 0)},
        {"id_key": "Applied > Rejected", "type": "status", "name": f"Applied > Rejected ({status_counts.get('Applied > Rejected', 0)})", "column": 2, "color": "#e74c3c", "count": status_counts.get('Applied > Rejected', 0)},
        {"id_key": "Screened", "type": "status", "name": f"Screened ({combined_screened})", "column": 2, "color": "#2ecc71", "count": combined_screened},
        
        # Column 3: Dedicated Deep Stages
        {"id_key": "Screened > No Response", "type": "status", "name": f"Screened > No Response ({status_counts.get('Screened > No Response', 0)})", "column": 3, "color": "#f1c40f", "count": status_counts.get('Screened > No Response', 0)},
        {"id_key": "Screened > Rejected", "type": "status", "name": f"Screened > Rejected ({status_counts.get('Screened > Rejected', 0)})", "column": 3, "color": "#e74c3c", "count": status_counts.get('Screened > Rejected', 0)}
    ]

    nodes_config = [node for node in raw_nodes_config if node["count"] > 0]
    active_keys = {n["id_key"] for n in nodes_config}

    node_name_to_idx = {n["name"]: i for i, n in enumerate(nodes_config)}
    
    root_node_name = f"Applied ({total_applied})"
    source_to_node = {src: f"{src} ({source_counts.get(src, 0)})" for src in source_counts.keys()}
    
    shared_screened_label = f"Screened ({combined_screened})"
    status_to_node = {
        'Applied': f"Active / In Review ({status_counts.get('Applied', 0)})",
        'Applied > No Response': f"Applied > No Response ({status_counts.get('Applied > No Response', 0)})",
        'Applied > Rejected': f"Applied > Rejected ({status_counts.get('Applied > Rejected', 0)})",
        'Screened': shared_screened_label,
        'Screened > No Response': shared_screened_label,
        'Screened > Rejected': shared_screened_label
    }

    links_raw = []

    for _, row in df_clean.iterrows():
        src = row['Source']
        status = row['Status']
        if status not in valid_statuses or src not in source_to_node:
            continue

        if src not in active_keys or "TotalApplied" not in active_keys:
            continue

        src_node = source_to_node[src]
        
        if status in ['Screened > No Response', 'Screened > Rejected']:
            if "Screened" in active_keys and status in active_keys:
                dest_node = shared_screened_label
                col4_node_name = f"Screened > No Response ({status_counts.get('Screened > No Response', 0)})" if status == 'Screened > No Response' else f"Screened > Rejected ({status_counts.get('Screened > Rejected', 0)})"
                links_raw.append({"source": src_node, "target": root_node_name})
                links_raw.append({"source": root_node_name, "target": dest_node})
                links_raw.append({"source": dest_node, "target": col4_node_name})
        else:
            if status == 'Screened' and "Screened" not in active_keys:
                continue
            if status in status_to_node and status in active_keys:
                dest_node = status_to_node[status]
                links_raw.append({"source": src_node, "target": root_node_name})
                links_raw.append({"source": root_node_name, "target": dest_node})

    links_config = []
    if links_raw:
        links_df = pd.DataFrame(links_raw).groupby(['source', 'target']).size().reset_index(name='value')
        for _, r in links_df.iterrows():
            if r['source'] in node_name_to_idx and r['target'] in node_name_to_idx:
                links_config.append({
                    "source": node_name_to_idx[r['source']],
                    "target": node_name_to_idx[r['target']],
                    "value": int(r['value'])
                })

    for n in nodes_config:
        n.pop("id_key", None)
        n.pop("type", None)
        n.pop("count", None)

    d3_data_json = json.dumps({"nodes": nodes_config, "links": links_config})

    print("👉 Compiling D3.js Layout Template with Path Highlighting...")
    
    html_template = f"""<!DOCTYPE html>
    <html>
    <head>
        <title>Jira Application Source Pipeline (D3.js)</title>
        <script src="https://d3js.org/d3.v7.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12.3/dist/d3-sankey.min.js"></script>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f6f9; padding: 30px; margin: 0; display: flex; flex-direction: column; align-items: center; }}
            .container {{ width: 1250px; background: white; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); padding: 25px; box-sizing: border-box; }}
            .header {{ text-align: left; margin-bottom: 25px; }}
            .header h2 {{ color: #2c3e50; margin: 0 0 5px 0; }}
            .header p {{ color: #7f8c8d; margin: 0; font-size: 14px; }}
            .node rect {{ fill-opacity: 0.95; shape-rendering: geometricPrecision; stroke: #ffffff; stroke-width: 2px; cursor: pointer; }}
            .node rect:hover {{ filter: brightness(1.05); }}
            .node text {{ font-size: 12px; font-weight: bold; fill: #2c3e50; pointer-events: none; }}
            .link {{ fill: none; stroke-opacity: 0.28; transition: stroke-opacity 0.2s, opacity 0.2s; }}
            .link:hover {{ stroke-opacity: 0.6 !important; }}
            #tooltip {{ position: absolute; padding: 8px 12px; background: rgba(44, 62, 80, 0.95); color: white; border-radius: 4px; font-size: 12px; pointer-events: none; opacity: 0; transition: opacity 0.15s ease; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }}
            
            .faded {{ opacity: 0.08 !important; }}
            .highlighted-link {{ stroke-opacity: 0.75 !important; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Jira Application Source Pipeline</h2>
                <p>
                    Interactive 4-Column Pipeline built natively with <strong>D3.js</strong>. 
                    <span style="color: #2980b9; font-weight: bold; display: block; margin-top: 4px;">💡 Click any node to trace its direct path. Click the canvas background to reset.</span>
                    <span style="display: block; margin-top: 8px; color: #95a5a6; font-weight: bold;">
                        ⏰ Last Synchronized: <span id="local-timestamp">Calculating local time...</span>
                    </span>
                </p>
            </div>
            <svg id="sankey_svg" width="1200" height="550"></svg>
        </div>
        <div id="tooltip"></div>

        <script>
            const graphData = {d3_data_json};

            const svg = d3.select("#sankey_svg"),
                  width = +svg.attr("width"),
                  height = +svg.attr("height");

            // 🌟 FIXED background reset handler
            svg.on("click", function(event) {{
                if (event.target.tagName === "svg") {{
                    linkElements.classed("faded", false).classed("highlighted-link", false);
                    nodeElements.classed("faded", false);
                    isHighlighted = false;
                }}
            }});

            const sankey = d3.sankey()
                .nodeWidth(22)
                .nodePadding(32)
                .extent([[10, 10], [width - 180, height - 10]]);

            let graph = sankey(graphData);

            const totalCols = 4;
            const colWidth = (width - 220) / (totalCols - 1);

            graph.nodes.forEach(node => {{
                node.x0 = node.column * colWidth;
                node.x1 = node.x0 + sankey.nodeWidth();
            }});

            sankey.update(graph);

            const tooltip = d3.select("#tooltip");

            const defs = svg.append("defs");
            graph.links.forEach((link, i) => {{
                const gradientId = `grad-${{i}}`;
                const grad = defs.append("linearGradient")
                    .attr("id", gradientId)
                    .attr("gradientUnits", "userSpaceOnUse")
                    .attr("x1", link.source.x1)
                    .attr("x2", link.target.x0);

                grad.append("stop").attr("offset", "0%").attr("stop-color", link.source.color);
                grad.append("stop").attr("offset", "100%").attr("stop-color", link.target.color);
                link.gradientId = gradientId;
            }});

            const linkElements = svg.append("g")
                .attr("fill", "none")
                .selectAll("path")
                .data(graph.links)
                .enter().append("path")
                .attr("class", "link")
                .attr("d", d3.sankeyLinkHorizontal())
                .attr("stroke", (d, i) => `url(#grad-${{i}})`)
                .style("stroke-width", d => Math.max(1.5, d.width))
                .on("mouseover", function(event, d) {{
                    tooltip.style("opacity", 1)
                           .html(`${{d.source.name}} &rarr; ${{d.target.name}}<br/>Count: ${{d.value}}`);
                }})
                .on("mousemove", function(event) {{
                    tooltip.style("left", (event.pageX + 15) + "px")
                           .style("top", (event.pageY - 25) + "px");
                }})
                .on("mouseout", function() {{
                    tooltip.style("opacity", 0);
                }});

            const nodeElements = svg.append("g")
                .selectAll("g")
                .data(graph.nodes)
                .enter().append("g")
                .attr("class", "node")
                .attr("transform", d => `translate(${{d.x0}},${{d.y0}})`);

            let isHighlighted = false;

            nodeElements.append("rect")
                .attr("height", d => Math.max(4, d.y1 - d.y0))
                .attr("width", d => d.x1 - d.x0)
                .attr("rx", 5)
                .attr("ry", 5)
                .style("fill", d => d.color)
                .on("mouseover", function(event, d) {{
                    tooltip.style("opacity", 1).html(`${{d.name}}`);
                }})
                .on("mousemove", function(event) {{
                    tooltip.style("left", (event.pageX + 15) + "px")
                           .style("top", (event.pageY - 25) + "px");
                }})
                .on("mouseout", function() {{
                    tooltip.style("opacity", 0);
                }})
                .on("click", function(event, clickedNode) {{
                    event.stopPropagation();
                    
                    const dynamicConnectedNodes = new Set();
                    const dynamicConnectedLinks = new Set();
                    
                    dynamicConnectedNodes.add(clickedNode.index);
                    
                    // Trace downstream flow paths
                    let processingQueue = [clickedNode];
                    while(processingQueue.length > 0) {{
                        let current = processingQueue.shift();
                        current.sourceLinks.forEach(l => {{
                            dynamicConnectedLinks.add(l);
                            dynamicConnectedNodes.add(l.target.index);
                            processingQueue.push(l.target);
                        }});
                    }}
                    
                    // Trace upstream flow paths
                    processingQueue = [clickedNode];
                    while(processingQueue.length > 0) {{
                        let current = processingQueue.shift();
                        current.targetLinks.forEach(l => {{
                            dynamicConnectedLinks.add(l);
                            dynamicConnectedNodes.add(l.source.index);
                            processingQueue.push(l.source);
                        }});
                    }}
                    
                    // Toggle visibility states
                    linkElements.classed("faded", l => !dynamicConnectedLinks.has(l))
                                .classed("highlighted-link", l => dynamicConnectedLinks.has(l));
                                
                    nodeElements.classed("faded", n => !dynamicConnectedNodes.has(n.index));
                    isHighlighted = true;
                }});

            nodeElements.append("text")
                .attr("x", d => d.x1 - d.x0 + 12)
                .attr("y", d => (d.y1 - d.y0) / 2)
                .attr("dy", "0.35em")
                .attr("text-anchor", "start")
                .text(d => d.name);

            const pipelineUtcTime = new Date("{current_utc_iso}");
            document.getElementById("local-timestamp").innerText = pipelineUtcTime.toLocaleString(undefined, {{dateStyle: "long", timeStyle: "short"}});
        </script>
    </body>
    </html>
    """

    with open("application_sankey.html", "w", encoding="utf-8") as file:
        file.write(html_template)

    print("\n🎉 INTERACTIVE PATH TRACING ACTIVATED!")
    print("-> Web asset updated locally as 'application_sankey.html'")