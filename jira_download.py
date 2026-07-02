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
        if src_lower == 'dad': return 'Dad'
        if src_lower == 'scoutify': return 'Scoutify'
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
        {"id_key": "Dad", "type": "source", "name": f"Dad ({source_counts.get('Dad', 0)})", "column": 0, "color": "#d4af37", "count": source_counts.get('Dad', 0)},
        {"id_key": "Indeed", "type": "source", "name": f"Indeed ({source_counts.get('Indeed', 0)})", "column": 0, "color": "#2164f3", "count": source_counts.get('Indeed', 0)},
        {"id_key": "LinkedIn", "type": "source", "name": f"LinkedIn ({source_counts.get('LinkedIn', 0)})", "column": 0, "color": "#0072b1", "count": source_counts.get('LinkedIn', 0)},
        {"id_key": "Me", "type": "source", "name": f"Me ({source_counts.get('Me', 0)})", "column": 0, "color": "#27a6f5", "count": source_counts.get('Me', 0)},
        {"id_key": "Networking", "type": "source", "name": f"Networking ({source_counts.get('Networking', 0)})", "column": 0, "color": "#fa9214", "count": source_counts.get('Networking', 0)},
        {"id_key": "Scoutify", "type": "source", "name": f"Scoutify ({source_counts.get('Scoutify', 0)})", "column": 0, "color": "#7bcd9d", "count": source_counts.get('Scoutify', 0)},
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
                links_raw.append({"source": src_node, "target": root_node_name, "origin": src})
                links_raw.append({"source": root_node_name, "target": dest_node, "origin": src})
                links_raw.append({"source": dest_node, "target": col4_node_name, "origin": src})
        else:
            if status == 'Screened' and "Screened" not in active_keys:
                continue
            if status in status_to_node and status in active_keys:
                dest_node = status_to_node[status]
                links_raw.append({"source": src_node, "target": root_node_name, "origin": src})
                links_raw.append({"source": root_node_name, "target": dest_node, "origin": src})

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

    for n in nodes_config:
        n.pop("id_key", None)
        n.pop("type", None)
        n.pop("count", None)

    d3_data_json = json.dumps({"nodes": nodes_config, "links": links_config})

    print("👉 Compiling D3.js Layout Template with Proportional Isolation & Fluid Layout...")
    
    html_template = f"""<!DOCTYPE html>
    <html>
    <head>
        <title>Jira Application Source Pipeline (D3.js)</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://d3js.org/d3.v7.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12.3/dist/d3-sankey.min.js"></script>
        <style>
            body {{ 
                font-family: Arial, sans-serif; 
                background-color: #f4f6f9; 
                padding: 10px; 
                margin: 0; 
                display: flex; 
                flex-direction: column; 
                align-items: center; 
            }}
            .container {{ 
                width: 100%; 
                max-width: 1250px; 
                background: white; 
                border-radius: 8px; 
                box-shadow: 0 4px 12px rgba(0,0,0,0.08); 
                padding: 15px; 
                box-sizing: border-box; 
                position: relative; 
            }}
            .header {{ text-align: left; margin-bottom: 25px; }}
            .header h2 {{ color: #2c3e50; margin: 0 0 5px 0; font-size: 1.5rem; }}
            .header p {{ color: #7f8c8d; margin: 0; font-size: 13px; }}
            
            .svg-wrapper {{
                width: 100%;
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
            }}
            #sankey_svg {{ 
                width: 100%; 
                height: auto; 
                min-width: 850px;
            }}
            
            .node rect {{ fill-opacity: 0.95; shape-rendering: geometricPrecision; stroke: #ffffff; stroke-width: 2px; cursor: pointer; }}
            .node rect:hover {{ filter: brightness(1.05); }}
            .node text {{ font-size: 11px; font-weight: bold; fill: #2c3e50; pointer-events: none; }}
            .link {{ fill: none; stroke-opacity: 0.28; transition: stroke-opacity 0.2s, opacity 0.2s, stroke-width 0.2s; }}
            .link:hover {{ stroke-opacity: 0.6 !important; }}
            #tooltip {{ position: absolute; padding: 8px 12px; background: rgba(44, 62, 80, 0.95); color: white; border-radius: 4px; font-size: 12px; pointer-events: none; opacity: 0; transition: opacity 0.15s ease; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.2); z-index: 100; }}
            
            #cohort-hud {{ 
                position: relative; 
                top: 0; 
                right: 0; 
                background: #2c3e50; 
                color: white; 
                padding: 15px; 
                border-radius: 6px; 
                box-shadow: 0 4px 10px rgba(0,0,0,0.15); 
                font-size: 12px; 
                display: none; 
                width: 100%; 
                box-sizing: border-box; 
                line-height: 1.5;
                margin-bottom: 15px;
            }}
            #cohort-hud h4 {{ margin: 0 0 8px 0; color: #2ecc71; border-bottom: 1px solid rgba(255,255,255,0.2); padding-bottom: 4px; font-size: 13px; }}
            #cohort-hud ul {{ margin: 0; padding-left: 18px; }}
            
            @media (min-width: 768px) {{
                body {{ padding: 30px; }}
                .container {{ padding: 25px; }}
                .header h2 {{ font-size: 1.8rem; }}
                #cohort-hud {{ position: absolute; top: 25px; right: 25px; width: 280px; margin-bottom: 0; }}
                .node text {{ font-size: 12px; }}
            }}

            .faded {{ opacity: 0.04 !important; }}
            .highlighted-link {{ stroke-opacity: 0.8 !important; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Jira Application Source Pipeline</h2>
                <p>
                    Interactive 4-Column Pipeline built natively with <strong>D3.js</strong>. 
                    <span style="color: #16a085; font-weight: bold; display: block; margin-top: 4px;">🚀 Exact Path Decomposition Active: Clicking a status dynamically rescales upstream link thickness to reflect ONLY the true count coming from each platform.</span>
                    <span style="display: block; margin-top: 8px; color: #95a5a6; font-weight: bold;">
                        ⏰ Last Synchronized: <span id="local-timestamp">Calculating local time...</span>
                    </span>
                </p>
            </div>
            <div id="cohort-hud"></div>
            <div class="svg-wrapper">
                <svg id="sankey_svg" viewBox="0 0 1200 550" preserveAspectRatio="xMinYMin meet"></svg>
            </div>
        </div>
        <div id="tooltip"></div>

        <script>
            const graphData = {d3_data_json};

            // Deep clone original line widths for scaling operations
            graphData.links.forEach(l => {{
                l.originalWidth = l.width;
            }});

            const svg = d3.select("#sankey_svg"),
                  width = 1200,
                  height = 550;

            svg.on("click", function(event) {{
                if (event.target.tagName === "svg") {{
                    resetSankeyEffects();
                }}
            }});

            function resetSankeyEffects() {{
                linkElements.classed("faded", false).classed("highlighted-link", false)
                            .style("stroke-width", d => Math.max(1.5, d.originalWidth));
                nodeElements.classed("faded", false);
                d3.select("#cohort-hud").style("display", "none");
                isHighlighted = false;
            }}

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
                .attr("data-origin-source", d => d.origin_source)
                .on("mouseover", function(event, d) {{
                    let displayVal = d.value;
                    if (isHighlighted && d.currentScaledValue !== undefined) {{
                        displayVal = `${{d.currentScaledValue}} of ${{d.value}}`;
                    }}
                    tooltip.style("opacity", 1)
                           .html(`${{d.source.name}} &rarr; ${{d.target.name}}<br/>Cohort Volume: ${{displayVal}}`);
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
                    
                    const activeNodes = new Set();
                    const activeLinks = new Set();
                    activeNodes.add(clickedNode.index);

                    // Reset link references
                    graph.links.forEach(l => l.currentScaledValue = undefined);

                    // Case A: Clicking Column 0 (Sourcing Channels) - Forward pass + Downstream HUD
                    if (clickedNode.column === 0) {{
                        let platformFilter = clickedNode.name.split(" (")[0];
                        let downstreamStatuses = {{}};

                        linkElements.each(function(l) {{
                            if (l.origin_source === platformFilter) {{
                                activeLinks.add(l);
                                activeNodes.add(l.source.index);
                                activeNodes.add(l.target.index);

                                // Capture the final status targets (Columns 2 and 3)
                                if (l.target.column >= 2) {{
                                    let statusName = l.target.name.split(" (")[0];
                                    // If it's the combined Screened node, skip it to avoid double-counting the sub-stages
                                    if (statusName === "Screened" && l.target.column === 2 && clickedNode.sourceLinks.some(sl => sl.target.column === 3)) {{
                                        return;
                                    }}
                                    downstreamStatuses[statusName] = (downstreamStatuses[statusName] || 0) + l.value;
                                }}
                            }}
                        }});

                        // Generate HUD overlay detailing specific downstream distribution
                        let hudHtml = `<h4>${{platformFilter}} Status Breakdown</h4><ul>`;
                        Object.keys(downstreamStatuses).sort((a,b) => downstreamStatuses[b] - downstreamStatuses[a]).forEach(s => {{
                            hudHtml += `<li><strong>${{s}}</strong>: ${{downstreamStatuses[s]}} application(s)</li>`;
                        }});
                        hudHtml += "</ul><p style='margin:10px 0 0 0; font-size:10px; color:#bdc3c7;'>Click chart background to clear.</p>";
                        
                        d3.select("#cohort-hud").html(hudHtml).style("display", "block");
                    }}
                    // Case B: Clicking Column 1 (Total Consolidation)
                    else if (clickedNode.column === 1) {{
                        linkElements.each(function(l) {{
                            activeLinks.add(l);
                            activeNodes.add(l.source.index);
                            activeNodes.add(l.target.index);
                        }});
                        d3.select("#cohort-hud").style("display", "none");
                    }}
                    // Case C: Target Node Status Click (Column 2 or 3) - PROPORTIONAL BREAKDOWN PATH ISOLATION
                    else {{
                        let exactSlices = {{}};
                        let targetLinksToEvaluate = [];

                        if (clickedNode.column === 3) {{
                            clickedNode.targetLinks.forEach(l => {{
                                activeLinks.add(l);
                                activeNodes.add(l.source.index);
                                targetLinksToEvaluate.push(l);
                            }});
                        }} else {{
                            clickedNode.targetLinks.forEach(l => targetLinksToEvaluate.push(l));
                        }}

                        targetLinksToEvaluate.forEach(link => {{
                            let platform = link.origin_source;
                            let volume = link.value;
                            exactSlices[platform] = (exactSlices[platform] || 0) + volume;
                        }});

                        clickedNode.targetLinks.forEach(l => {{ activeLinks.add(l); activeNodes.add(l.source.index); }});
                        clickedNode.sourceLinks.forEach(l => {{ activeLinks.add(l); activeNodes.add(l.target.index); }});

                        linkElements.each(function(l) {{
                            if (l.source.column === 0 && l.target.column === 1) {{
                                if (exactSlices[l.origin_source] !== undefined) {{
                                    activeLinks.add(l);
                                    activeNodes.add(l.source.index);
                                    
                                    let targetedCount = exactSlices[l.origin_source];
                                    l.currentScaledValue = targetedCount;
                                    
                                    let scaleFactor = targetedCount / l.value;
                                    let adjustedWidth = l.originalWidth * scaleFactor;
                                    
                                    d3.select(this).style("stroke-width", Math.max(2, adjustedWidth));
                                }}
                            }}
                        }});

                        let cleanTitle = clickedNode.name.split(" (")[0];
                        let hudHtml = `<h4>${{cleanTitle}} Source Cohorts</h4><ul>`;
                        Object.keys(exactSlices).sort((a,b) => exactSlices[b] - exactSlices[a]).forEach(p => {{
                            hudHtml += `<li><strong>${{p}}</strong>: ${{exactSlices[p]}} application(s)</li>`;
                        }});
                        hudHtml += "</ul><p style='margin:10px 0 0 0; font-size:10px; color:#bdc3c7;'>Click chart background to clear.</p>";
                        
                        d3.select("#cohort-hud").html(hudHtml).style("display", "block");
                    }}
                    
                    linkElements.classed("faded", l => !activeLinks.has(l))
                                .classed("highlighted-link", l => activeLinks.has(l));
                                
                    nodeElements.classed("faded", n => !activeNodes.has(n.index));
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

    print("\n🎉 SMART DATA COHORT TRACKING ACTIVATED!")
    print("-> Web asset updated locally as 'application_sankey.html'")