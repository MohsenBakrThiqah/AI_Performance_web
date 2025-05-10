import os
import json
import re
import shutil
import time
import logging
import openai
import zipfile
import tempfile
from urllib.parse import urlparse
import html

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def generate_jmeter_report(folder_path, form_data):
    """Generate JMeter report from the provided folder and form data"""
    try:
        # Handle input if it's a zip file
        if folder_path.lower().endswith('.zip'):
            temp_extract_dir = tempfile.mkdtemp(prefix="jmeter_extract_")
            with zipfile.ZipFile(folder_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)
            folder_path = temp_extract_dir  # Update folder_path to extracted content

        # Create output directory
        output_dir = os.path.join(tempfile.mkdtemp(prefix="jmeter_report_"), 'generated_report')
        os.makedirs(output_dir, exist_ok=True)

        # Copy original files to output directory
        for item in os.listdir(folder_path):
            src = os.path.join(folder_path, item)
            dst = os.path.join(output_dir, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

        # Process files
        html_file_path = os.path.join(output_dir, 'index.html')
        js_file_path = os.path.join(output_dir, 'content/js/dashboard.js')
        statistics_file_path = os.path.join(output_dir, 'statistics.json')

        # Edit HTML and JS files
        edit_html_and_js(html_file_path, js_file_path, statistics_file_path, form_data)

        # Edit statistics table
        edit_statistics_table(js_file_path, form_data)

        # Set pass/fail colors
        pass_fail_colors(js_file_path, os.path.join(output_dir, 'content/css/dashboard.css'),
                         form_data['api_threshold'], form_data['err_rate_threshold'])

        # Zip the final report
        zip_output_path = f"{output_dir}.zip"
        shutil.make_archive(output_dir, 'zip', output_dir)

        # Clean up temporary directories
        shutil.rmtree(folder_path if folder_path != temp_extract_dir else folder_path)

        return zip_output_path

    except Exception as e:
        logging.error(f"Error generating report: {str(e)}")
        raise


def edit_html_and_js(html_path, js_path, stats_path, form_data):
    """Edit the HTML and JS files with the provided form data"""
    try:
        with open(stats_path, 'r', encoding='utf-8') as json_file:
            statistics_content = json_file.read()

        # HTML edits
        with open(html_path, 'r', encoding='utf-8') as html_file:
            html_content = html_file.read()

        # Replace APDEX table with custom data
        old_html_content = '''<p class="dashboard-title"><a href="https://en.wikipedia.org/wiki/Apdex" target="_blank">APDEX (Application Performance Index)</a></p>'''
        new_html_content = generate_custom_html(form_data)
        modified_html = html_content.replace(old_html_content, new_html_content)

        # Add other HTML modifications
        modified_html = modified_html.replace("Apache JMeter Dashboard",
                                              f"THIQAH Confidential: {form_data['project_name']} Performance Test Report")
        print(os.path.join(os.getcwd(), "static", "images", "Cover.png"))
        modified_html = modified_html.replace("</title>",
                                              "</title><img src=\"" + os.path.join(os.getcwd(), "static", "images", "Cover.png") + "\" alt=\"Cover Image\" style=\"width: "
                                                                                "100%; height: 100vh; object-fit: cover; "
                                                                                "break-after: page; display: none;\" "
                                                                                "onload=\"this.style.display='none'; "
                                                                                "window.matchMedia('print').addListener("
                                                                                "mql => mql.matches &amp;&amp; ("
                                                                                "this.style.display='block')); "
                                                                                "window.onafterprint = () => "
                                                                                "this.style.display='none';\">")
        modified_html = modified_html.replace("Filter for display", "Findings")

        # Add logo and header
        modified_html = modified_html.replace(
            "<title>Apache JMeter Dashboard</title>",
            "<title>THIQAH Performance Test Report</title>"
        )

        # Update project name in source file
        modified_html = re.sub(
            r'<tr>\s*<td>Source file<\/td>\s*<td>.*<\/td>\s*<\/tr>',
            f'<tr><td>Project Name</td><td>{form_data["project_name"]}</td></tr>',
            modified_html
        )

        # Add navigation link
        modified_html = modified_html.replace(
            '<a href="index.html"><i class="fa fa-dashboard fa-fw"></i> Dashboard</a>',
            '<a href="index.html"><i class="fa fa-dashboard fa-fw"></i> Dashboard</a>\n<a href="content/Reports"><i class="fa fa-dashboard fa-fw"></i> Reports History</a>'
        )

        # Add findings
        findings = [v for k, v in form_data.items() if k.startswith('finding_') and v]
        findings_html = "<br>".join([f"{i + 1}. {finding}" for i, finding in enumerate(findings)])
        print(findings_html)
        modified_html = re.sub(
            r'<tr>\s*<td>Findings</td>\s*<td>""</td>\s*</tr>',
            f'<tr><td>Findings</td><td>{findings_html}</td></tr>',
            modified_html
        )
        modified_html = modified_html.replace("</body>", "<img src=\"" + os.path.join(os.getcwd(), "static", "images", "Thanks.png") + "\" alt=\"Cover Image\" style=\"width: 100%; height: 100vh; object-fit: cover; break-after: page; display: none;\" onload=\"this.style.display='none'; window.matchMedia('print').addListener(mql => mql.matches &amp;&amp; (this.style.display='block')); window.onafterprint = () => this.style.display='none';\"></body>")
        # GPT analysis if enabled
        if form_data.get('use_gpt', False):
            gpt_response = ask_gpt(statistics_content, form_data)
            errors_analysis = analyze_errors(js_path)
            if errors_analysis:
                gpt_response += f"<br><br><p class='dashboard-title'>OpenAI - Errors Investigation Recommendation</p>{errors_analysis}"

            gpt_response = gpt_response.replace('\n', '<br>').replace('#', '').replace('*', '')

            modified_html = modified_html.replace(
                '<script src="sbadmin2-1.0.7/bower_components/jquery/dist/jquery.min.js"></script>',
                f'<script src="sbadmin2-1.0.7/bower_components/jquery/dist/jquery.min.js"></script>\n<br><br><p class="dashboard-title">OpenAI Statistics Analysis</p>{gpt_response}'
            )

        # Save modified HTML
        with open(html_path, 'w', encoding='utf-8') as html_file:
            html_file.write(modified_html)

        # JS edits
        with open(js_path, 'r', encoding='utf-8') as js_file:
            js_content = js_file.read()

        # Remove APDEX table creation
        part_to_remove = r'// Creates APDEX table.*?// Create statistics table'
        modified_js = re.sub(part_to_remove, '', js_content, flags=re.DOTALL)

        with open(js_path, 'w', encoding='utf-8') as js_file:
            js_file.write(modified_js)

    except Exception as e:
        logging.error(f"Error editing HTML/JS: {str(e)}")
        raise


def analyze_errors(js_path):
    """Analyze errors from the dashboard.js file"""
    try:
        with open(js_path, 'r', encoding='utf-8') as js_file:
            js_content = js_file.read()

        pattern = re.compile(r'createTable\(\$\("#errorsTable"\), (\{.*?\}), function', re.DOTALL)
        pattern2 = re.compile(r'createTable\(\$\("#top5ErrorsBySamplerTable"\), (\{.*?\}), function', re.DOTALL)

        match = pattern.search(js_content)
        match2 = pattern2.search(js_content)

        if match and match2:
            errors_analysis = "First JSON object:\n" + match.group(1) + "\n\n Second JSON object:\n" + match2.group(1)
            return ask_gpt_errors(errors_analysis)
        return None

    except Exception as e:
        logging.error(f"Error analyzing errors: {str(e)}")
        return None


def ask_gpt_errors(prompt):
    """Get error analysis from GPT"""
    try:
        openai.api_key = "sk-proj-3LEJyNSnWV3CPZKTt0WuT3BlbkFJgud3qBm7ZQVfZd9ojuL3"  # Should be set in environment

        completion = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system",
                 "content": "You are a Performance test engineer, having the error results of load test as JSON file generated from JMeter as follow:" + prompt},
                {"role": "user",
                 "content": "in one section and short lines, provide me with recommendations where to investigate to find the root cause of these error, also provide me with the possible reasons that caused these errors, if you didn't find any errors in provided JSON respond that no errors found for this test so no need for any analysis"}
            ]
        )

        return completion['choices'][0]['message']['content']
    except Exception as e:
        logging.error(f"Error getting GPT error analysis: {str(e)}")
        return None


def generate_custom_html(form_data):
    """Generate the custom HTML table with test details"""
    return f'''
        <p class="dashboard-title">Test Report Detailed Results</p>
        </div>
        <div class="panel-body">
            <section id="apdex" class="col-md-12 table-responsive">
                <table id="apdexTable" class="table table-bordered table-condensed tablesorter ">
                    <tr>
                        <td>Performance Engineer Name</td>
                        <td>{form_data.get('engineer_name', '')}</td>
                    </tr>
                    <tr>
                        <td>URL Under Test</td>
                        <td>{form_data.get('url', '')}</td>
                    </tr>
                    <tr>
                        <td>Test Round</td>
                        <td>{form_data.get('test_round', '')}</td>
                    </tr>
                    <tr>
                        <td>Test Round Results</td>
                        <td>{form_data.get('round_status', '')}</td>
                    </tr>
                    <tr>
                        <td>Test Type</td>
                        <td>{form_data.get('test_type', '')}</td>
                    </tr>
                    <tr>
                        <td>Number of CUs</td>
                        <td>{form_data.get('cu', '')}</td>
                    </tr>
                    <tr>
                        <td>Ramp up in min</td>
                        <td>{form_data.get('ramp_up', '')}</td>
                    </tr>
                    <tr>
                        <td>Test Duration in min</td>
                        <td>{form_data.get('duration', '')}</td>
                    </tr>
                    <tr>
                        <td>Web Transactions Compliant?</td>
                        <td>{form_data.get('web_trans_status', '')}</td>
                    </tr>
                    <tr>
                        <td>API Transactions Compliant?</td>
                        <td>{form_data.get('api_trans_status', '')}</td>
                    </tr>
                    <tr>
                        <td>Error % Compliant?</td>
                        <td>{form_data.get('error_rate_status', '')}</td>
                    </tr>
                    <tr>
                        <td>API 90% Threshold (ms)</td>
                        <td>{form_data.get('api_threshold', '')}</td>
                    </tr>
                    <tr>
                        <td>Error % Threshold</td>
                        <td>{form_data.get('err_rate_threshold', '')}</td>
                    </tr>
                    <tr>
                        <td>Azure New Bugs IDs</td>
                        <td>{form_data.get('new_bugs', '')}</td>
                    </tr>
                    <tr>
                        <td>Azure Reopened Bugs IDs</td>
                        <td>{form_data.get('reopened_bugs', '')}</td>
                    </tr>
                    <tr>
                        <td>Azure Release Report</td>
                        <td>{form_data.get('release_report', '')}</td>
                    </tr>
                    <tr>
                        <td>Test Scope</td>
                        <td>{form_data.get('scope', '').replace('n', '<br>')}</td>
                    </tr>
                </table>
    '''


def ask_gpt(statistics_content, form_data):
    """Get analysis from GPT"""
    try:
        openai.api_key = "sk-proj-3LEJyNSnWV3CPZKTt0WuT3BlbkFJgud3qBm7ZQVfZd9ojuL3"  # Should be set in environment

        completion = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a Performance test engineer"},
                {"role": "user",
                 "content": f"Here is the performance test result data from JMeter: \n\n{statistics_content}\n\nCreate a comprehensive analysis with the following Criteria: Thiqah standards\n\n Accepted pct1ResTime (90% Line): Up to {form_data['api_threshold']} millisecond.\n Accepted errorPct: Up to {form_data['err_rate_threshold']}.00 ,if lower then passed. \n\nFirst Section: Summary for the analysis.\nSecond section: short summary for requests that have the highest impact for application slowness."}
            ]
        )

        return completion['choices'][0]['message']['content']
    except Exception as e:
        logging.error(f"Error getting GPT analysis: {str(e)}")
        return "GPT analysis failed due to an error"


def edit_statistics_table(js_file_path, form_data):
    """Edit the statistics table in the dashboard.js file"""
    try:
        with open(js_file_path, 'r', encoding='utf-8') as js_file:
            js_content = js_file.read()

        # Extract and modify the statistics table JSON
        pattern = re.compile(r'statisticsTable"\), (.+?), function', re.DOTALL)
        match = pattern.search(js_content)

        if not match:
            raise ValueError("Could not find statistics table configuration in JS file")

        json_str = match.group(1).strip()
        json_data = json.loads(json_str)

        # Format numbers to 2 decimal places
        def format_numbers(obj):
            if isinstance(obj, list):
                return [format_numbers(item) for item in obj]
            elif isinstance(obj, dict):
                return {key: format_numbers(value) for key, value in obj.items()}
            elif isinstance(obj, (int, float)):
                return round(obj, 2)
            return obj

        json_data = format_numbers(json_data)

        # Titles to remove
        titles_to_remove = ["FAIL", "Median", "95th pct", "99th pct"]
        indices_to_remove = [json_data["titles"].index(title) for title in titles_to_remove if
                             title in json_data["titles"]]

        # Remove titles and corresponding data
        json_data["titles"] = [title for i, title in enumerate(json_data["titles"]) if i not in indices_to_remove]
        json_data["overall"]["data"] = [value for i, value in enumerate(json_data["overall"]["data"]) if
                                        i not in indices_to_remove]

        for item in json_data["items"]:
            item["data"] = [value for i, value in enumerate(item["data"]) if i not in indices_to_remove]

        # Update the JS content with modified JSON
        new_json_str = json.dumps(json_data, indent=4)
        new_js_content = js_content[:match.start(1)] + new_json_str + js_content[match.end(1):]

        # Additional JS modifications
        new_js_content = re.sub(r'cell\.colSpan\s*=\s*7;', 'cell.colSpan = 1;', new_js_content)
        new_js_content = re.sub(
            r'cell\.colSpan\s*=\s*1;\s*cell\.innerHTML\s*=\s*"Response Times \(ms\)";',
            'cell.colSpan = 4;\n    cell.innerHTML = "Response Times (ms)";',
            new_js_content
        )
        new_js_content = re.sub(
            r'cell\.colSpan\s*=\s*3;\s*cell\.innerHTML\s*=\s*"Executions";',
            'cell.colSpan = 2;\n    cell.innerHTML = "Executions";',
            new_js_content
        )
        new_js_content = re.sub(
            r'//\s*Errors\s*pct\s*case\s*3:',
            '// Errors pct\n            case 2:',
            new_js_content
        )

        with open(js_file_path, 'w', encoding='utf-8') as js_file:
            js_file.write(new_js_content)

    except Exception as e:
        logging.error(f"Error editing statistics table: {str(e)}")
        raise


def pass_fail_colors(js_file_path, css_file_path, api_threshold, err_rate_threshold):
    """Add pass/fail color coding to the report"""
    try:
        # Add CSS styling for pass/fail
        with open(css_file_path, 'a', encoding='utf-8') as css_file:
            css_file.write(f"""
            /* Pass/Fail coloring */
            .green-text {{
                color: green;
            }}
            .red-text {{
                color: red;
            }}
            @media print {{
                .green-text {{
                    color: green !important;
                }}
                .red-text {{
                    color: red !important;
                }}
            }}
            """)

        # Add JavaScript for pass/fail coloring
        with open(js_file_path, 'r', encoding='utf-8') as js_file:
            js_content = js_file.read()

        # Replace the cell content line with enhanced version
        old_line = 'cell.innerHTML = formatter ? formatter(col, item.data[col]) : item.data[col];'
        new_lines = f"""
                    cell.innerHTML = formatter ? formatter(col, item.data[col]) : item.data[col];
                    // Check if the current column is "90th pct"
                    if (info.titles[col] === "90th pct") {{
                        var percentileValue = parseFloat(item.data[col]);
                        if (percentileValue < {api_threshold}) {{
                            cell.style.color = 'green';
                            cell.className = 'green-text';
                        }} else {{
                            cell.style.color = 'red';
                            cell.className = 'red-text';
                        }}
                    }}
                    // Check if the current column is "Error %"
                    if (info.titles[col] === "Error %") {{
                        var percentileValue = parseFloat(item.data[col]);
                        if (percentileValue < {err_rate_threshold}) {{
                            cell.style.color = 'green';
                            cell.className = 'green-text';
                        }} else {{
                            cell.style.color = 'red';
                            cell.className = 'red-text';
                        }}
                    }}
        """

        modified_js = js_content.replace(old_line, new_lines)

        with open(js_file_path, 'w', encoding='utf-8') as js_file:
            js_file.write(modified_js)

    except Exception as e:
        logging.error(f"Error adding pass/fail colors: {str(e)}")
        raise