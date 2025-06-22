import os
import json
import re
import shutil
# import time
import logging
# import openai
import zipfile
import tempfile
from urllib.parse import urlparse
# import html
import anthropic
import openai

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, OPENAI_API_KEY, OPENAI_MODEL

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
        # print(os.path.join(os.getcwd(), "static", "images", "Cover.png"))
        modified_html = modified_html.replace("</title>",
                                              "</title><img src=\"https://i.ibb.co/G35GLfK9/Cover.png\" alt=\"Cover Image\" style=\"width: "
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

        # Add findings - preserve whitespace and handle formatting
        findings_text = form_data.get('findings_text', '')
        
        # Process the findings text to preserve indentation and add formatting
        findings_lines = findings_text.split('\n')
        processed_lines = []
        
        # Track if the previous line was empty
        prev_line_empty = False
        
        for line in findings_lines:
            # Skip consecutive empty lines
            if not line.strip():
                if not prev_line_empty:  # Only add one empty line
                    processed_lines.append('')
                    prev_line_empty = True
                continue
            else:
                prev_line_empty = False
            
            # Handle bold text (**text**)
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            
            # Handle bullet points
            if line.strip().startswith('* ') or line.strip().startswith('- '):
                bullet_content = line.strip()[2:]
                # Count leading spaces before the bullet
                leading_spaces = len(line) - len(line.lstrip())
                # Create bullet point with proper indentation
                line = '&nbsp;' * leading_spaces + '• ' + bullet_content
            
            # Handle numbered lists (preserve the number)
            elif re.match(r'\s*\d+\.\s', line):
                # Keep the original formatting but ensure it's preserved in HTML
                leading_spaces = len(line) - len(line.lstrip())
                line = '&nbsp;' * leading_spaces + line.lstrip()
            
            # Handle other indentation
            elif line.startswith(' '):
                # Count leading spaces
                leading_spaces = len(line) - len(line.lstrip(' '))
                # Replace each leading space with &nbsp;
                line = '&nbsp;' * leading_spaces + line.lstrip(' ')
            
            processed_lines.append(line)
        
        # Use <p> tags for paragraphs instead of <br> for every line
        findings_html = ''
        current_paragraph = []
        
        for i, line in enumerate(processed_lines):
            if not line:  # Empty line indicates paragraph break
                if current_paragraph:
                    # Join the lines in this paragraph, but avoid adding <br> after formatting elements
                    paragraph_html = ''
                    for j, para_line in enumerate(current_paragraph):
                        # Check if this is a formatting line and there's a next line in this paragraph
                        is_strong = '</strong>' in para_line
                        # Improved regex pattern to better match numbered lists
                        is_numbered = bool(re.search(r'&nbsp;*\d+\.', para_line))
                        is_bullet = '• ' in para_line
                        is_last_in_paragraph = j == len(current_paragraph) - 1
                        
                        # Add the line
                        paragraph_html += para_line
                        
                        # Print debugging info
                        # print(f"Line: {para_line}, is_numbered: {is_numbered}, match: {re.search(r'&nbsp;*\d+\.', para_line)}")
                        
                        # Only add <br> if it's not a strong tag or numbered list
                        # Also don't add <br> if it's the last line in the paragraph
                        if not is_last_in_paragraph and not is_strong and not is_numbered:
                            paragraph_html += '<br>'
                    
                    findings_html += '<p>' + paragraph_html + '</p>'
                    current_paragraph = []
            else:
                current_paragraph.append(line)
        
        # Don't forget the last paragraph
        if current_paragraph:
            paragraph_html = ''
            for j, para_line in enumerate(current_paragraph):
                is_strong = '</strong>' in para_line
                # Improved regex pattern to better match numbered lists
                is_numbered = bool(re.search(r'&nbsp;*\d+\.', para_line))
                is_bullet = '• ' in para_line
                is_last_in_paragraph = j == len(current_paragraph) - 1
                
                paragraph_html += para_line
                
                # Only add <br> if it's not a strong tag or numbered list
                # Also don't add <br> if it's the last line in the paragraph
                if not is_last_in_paragraph and not is_strong and not is_numbered:
                    paragraph_html += '<br>'
            
            findings_html += '<p>' + paragraph_html + '</p>'
        
        # Add CSS for better whitespace handling
        css_for_whitespace = """
        <style>
        .preserve-whitespace {
            white-space: pre-wrap;
            font-family: monospace;
        }
        .preserve-whitespace p {
            margin-bottom: 0.5em;
        }
        .preserve-whitespace strong {
            color: #0d6efd;
        }
        </style>
        """
        
        modified_html = modified_html.replace('</head>', f'{css_for_whitespace}</head>')
        
        # Add CSS class for preserving whitespace
        modified_html = re.sub(
            r'<tr>\s*<td>Findings</td>\s*<td>""</td>\s*</tr>',
            f'<tr><td>Findings</td><td class="preserve-whitespace">{findings_html}</td></tr>',
            modified_html
        )
        
        modified_html = modified_html.replace("</body>", "<img src=\"https://i.ibb.co/8L9RQ6pB/Thanks.png\" alt=\"Cover Image\" style=\"width: 100%; height: 100vh; object-fit: cover; break-after: page; display: none;\" onload=\"this.style.display='none'; window.matchMedia('print').addListener(mql => mql.matches &amp;&amp; (this.style.display='block')); window.onafterprint = () => this.style.display='none';\"></body>")
        # GPT analysis if enabled
        if form_data.get('use_gpt', False):
            # gpt_response = ask_claude(statistics_content, form_data)
            gpt_response = ask_gpt(statistics_content, form_data)
            errors_analysis = analyze_errors(js_path)
            if errors_analysis:
                gpt_response += f"<br><br><p class='dashboard-title'>OpenAI GPT 4.1 - Errors Investigation Recommendation</p>{errors_analysis}"

            gpt_response = gpt_response.replace('\n', '<br>').replace('#', '').replace('*', '')

            modified_html = modified_html.replace(
                '<script src="sbadmin2-1.0.7/bower_components/jquery/dist/jquery.min.js"></script>',
                f'<script src="sbadmin2-1.0.7/bower_components/jquery/dist/jquery.min.js"></script>\n<br><br><p class="dashboard-title">OpenAI GPT 4.1 -  Statistics Analysis</p>{gpt_response}'
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
            # return ask_claude_errors(errors_analysis)
            return ask_gpt_errors(errors_analysis)
        return None

    except Exception as e:
        logging.error(f"Error analyzing errors: {str(e)}")
        return None


def ask_claude_errors(prompt):
    """Get error analysis from Claude"""
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=5000,
            messages=[
                {"role": "user",
                 "content": "You are a specialized Performance Test Engineer with extensive experience in analyzing JMeter test results. Your expertise includes identifying performance bottlenecks, error patterns, and root causes in load test data."
                            f"I need your expert analysis of these JMeter error results from a load test. The data is provided as JSON extracts from dashboard.js:\n\n{prompt}\n\n"
                            f"Please provide me with:\n"
                            f"1. A concise, actionable analysis of these errors\n"
                            f"2. Specific recommendations for where to investigate to find root causes\n"
                            f"3. The most likely reasons these errors occurred based on error patterns\n"
                            f"4. Any correlations between error types and specific transactions\n\n"
                            f"If no errors are found in the provided JSON, clearly state that no errors were detected and no analysis is needed.\n"
                            f"Format your response in short, well-organized paragraphs with clear headings."}
            ]
        )

        return response.content[0].text
    except Exception as e:
        logging.error(f"Error getting Claude error analysis: {str(e)}")
        return None

def ask_gpt_errors(prompt):
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_completion_tokens=100000,
            messages=[
                {"role": "system", "content": "You are a specialized Performance Test Engineer with extensive "
                                              "experience in analyzing JMeter test results. Your expertise includes "
                                              "identifying performance bottlenecks, error patterns, and root causes "
                                              "in load test data."},
                {"role": "user",
                 "content": f"I need your expert analysis of these JMeter error results from a load test. The data is provided as JSON extracts from dashboard.js:\n\n{prompt}\n\n"
                            f"Please provide me with:\n"
                            f"1. A concise, actionable analysis of these errors\n"
                            f"2. Specific recommendations for where to investigate to find root causes\n"
                            f"3. The most likely reasons these errors occurred based on error patterns\n"
                            f"4. Any correlations between error types and specific transactions\n\n"
                            f"If no errors are found in the provided JSON, clearly state that no errors were detected and no analysis is needed.\n"
                            f"Format your response in short, well-organized paragraphs with clear headings."}
            ]
        )

        content = response.choices[0].message.content
        return content
    except Exception as e:
        print("An error occurred while fetching response from GPT:", str(e))
        return None
def ask_claude(statistics_content, form_data):
    """Get analysis from Claude"""
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2000,
            messages=[
                {"role": "user",
                 "content": "You are a specialized Performance Test Engineer with extensive experience in analyzing JMeter test results. Your expertise includes identifying performance bottlenecks, error patterns, and root causes in load test data."
                            f"Please analyze these JMeter performance test results:\n\n{statistics_content}\n\n"
                            f"Thiqah Performance Standards:\n"
                            f"- 90th percentile response time threshold (pct1ResTime): {form_data['api_threshold']} ms or below\n"
                            f"- Error percentage threshold: {form_data['err_rate_threshold']}% or below\n\n"
                            f"Provide your analysis in these two distinct sections:\n"
                            f"1. EXECUTIVE SUMMARY: Overall test performance assessment with clear pass/fail status against Thiqah standards. Include key metrics, major bottlenecks, and critical findings.\n\n"
                            f"2. PERFORMANCE BOTTLENECKS: Detailed analysis of the specific requests with highest response times or error rates. Include specific transaction names, their metrics, and targeted recommendations for improvement.\n\n"
                            f"Focus on actionable insights that would help developers or system administrators improve performance. Be specific about which endpoints need attention."}
            ]
        )

        return response.content[0].text
    except Exception as e:
        logging.error(f"Error getting Claude analysis: {str(e)}")
        return "Claude analysis failed due to an error"


def ask_gpt(statistics_content, form_data):
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_completion_tokens=100000,
            messages=[
                {"role": "system",
                 "content": "You are a Performance test engineer"},
                {"role": "user",
                 "content": "You are a specialized Performance Test Engineer with extensive experience in analyzing JMeter test results. Your expertise includes identifying performance bottlenecks, error patterns, and root causes in load test data."
                            f"Please analyze these JMeter performance test results:\n\n{statistics_content}\n\n"
                            f"Thiqah Performance Standards:\n"
                            f"- 90th percentile response time threshold (pct1ResTime): {form_data['api_threshold']} ms or below\n"
                            f"- Error percentage threshold: {form_data['err_rate_threshold']}% or below\n\n"
                            f"Provide your analysis in these two distinct sections:\n"
                            f"1. EXECUTIVE SUMMARY: Overall test performance assessment with clear pass/fail status against Thiqah standards. Include key metrics, major bottlenecks, and critical findings.\n\n"
                            f"2. PERFORMANCE BOTTLENECKS: Detailed analysis of the specific requests with highest response times or error rates. Include specific transaction names, their metrics, and targeted recommendations for improvement.\n\n"
                            f"Focus on actionable insights that would help developers or system administrators improve performance. Be specific about which endpoints need attention."
                 }
            ]
        )

        content = response.choices[0].message.content
        return content
    except Exception as e:
        print("An error occurred while fetching response from GPT:", str(e))
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
                        <td>{'<br>'.join(line for line in form_data.get('scope', '').splitlines())}</td>
                    </tr>
                </table>
    '''


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