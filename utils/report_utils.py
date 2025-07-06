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
import requests
from urllib.parse import unquote
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
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
        
        # IMPORTANT: Remove the first insertion of the Thanks.png image
        # modified_html = modified_html.replace("</body>", "<img src=\"https://i.ibb.co/8L9RQ6pB/Thanks.png\" alt=\"Cover Image\" style=\"width: 100%; height: 100vh; object-fit: cover; break-after: page; display: none;\" onload=\"this.style.display='none'; window.matchMedia('print').addListener(mql => mql.matches &amp;&amp; (this.style.display='block')); window.onafterprint = () => this.style.display='none';\"></body>")
        
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

        # Add enhanced Kibana analysis processing with debugging
        try:
            # Log all form data to diagnose what's happening
            logging.info(f"Form data keys: {form_data.keys()}")
            logging.info(f"use_kibana_analysis value: {form_data.get('use_kibana_analysis')}")
            logging.info(f"APM service name: {form_data.get('APM_service_name')}")
            
            # IMPORTANT: Only check the value of use_kibana_analysis, not if the key exists
            use_kibana = form_data.get('use_kibana_analysis', False)
            
            # Convert to boolean if it's a string
            if isinstance(use_kibana, str):
                use_kibana = use_kibana.lower() in ('true', 'yes', 'y', 'on', '1')
            
            logging.info(f"Final Kibana analysis decision: {use_kibana}")
            
            if use_kibana:
                apm_service_name = form_data.get('APM_service_name', '')
                logging.info(f"Kibana analysis requested for service: {apm_service_name}")
                
                # Check if APM service name is valid
                if not apm_service_name.strip():
                    logging.error("APM service name is empty")
                    kibana_error_message = "No Data found on Kibana APM - Service name is missing"
                    
                    # Add error message to the report
                    body_pos = modified_html.find("</body>")
                    if body_pos != -1:
                        before_body = modified_html[:body_pos]
                        after_body = modified_html[body_pos:]
                        error_section = f'<br><br><p class="dashboard-title">OpenAI GPT 4.1 - Kibana APM Resource Utilization Analysis</p><p style="color:red">{kibana_error_message}</p>'
                        modified_html = before_body + error_section + after_body
                else:
                    # Call the analysis function with explicit exception handling
                    try:
                        logging.info("Calling ask_gpt_for_CPU_Memory function...")
                        KibanaAPMAnalysis = ask_gpt_for_CPU_Memory(form_data, html_path)
                        
                        if KibanaAPMAnalysis:
                            logging.info("Successfully received Kibana analysis")
                            kibana_analysis_html = KibanaAPMAnalysis.replace('\n', '<br>').replace('#', '').replace('*', '')
                            
                            # Find the body tag and insert before it
                            body_pos = modified_html.find("</body>")
                            if body_pos != -1:
                                # Remove any existing Thanks.png image if it's present
                                closing_img = '<img src=\"https://i.ibb.co/8L9RQ6pB/Thanks.png\"'
                                if closing_img in modified_html:
                                    img_pos = modified_html.find(closing_img)
                                    if img_pos != -1 and img_pos < body_pos:
                                        modified_html = modified_html[:img_pos] + modified_html[body_pos:]
                                        body_pos = modified_html.find("</body>")
                                
                                before_body = modified_html[:body_pos]
                                after_body = modified_html[body_pos:]
                                
                                # Construct the new content
                                kibana_section = f'<br><br><p class="dashboard-title">OpenAI GPT 4.1 - Kibana APM Resource Utilization Analysis</p>{kibana_analysis_html}'
                                
                                # Rebuild the HTML with the Kibana section
                                modified_html = before_body + kibana_section + after_body
                                logging.info("Successfully inserted Kibana analysis section")
                            else:
                                logging.error("Could not find </body> tag in HTML")
                        else:
                            logging.warning("No Kibana analysis data received")
                    except Exception as e:
                        logging.error(f"Error during Kibana analysis: {str(e)}")
                        kibana_error_message = f"Failed to generate Kibana analysis: {str(e)}"
                        
                        # Add error message to the report
                        body_pos = modified_html.find("</body>")
                        if body_pos != -1:
                            before_body = modified_html[:body_pos]
                            after_body = modified_html[body_pos:]
                            error_section = f'<br><br><p class="dashboard-title">OpenAI GPT 4.1 - Kibana APM Resource Utilization Analysis</p><p style="color:red">{kibana_error_message}</p>'
                            modified_html = before_body + error_section + after_body
            else:
                logging.info("Kibana analysis not requested - checkbox is not checked")
                
        except Exception as e:
            logging.error(f"Error in Kibana analysis processing: {str(e)}")
        
        # Make sure closing image is always added ONCE, at the very end of the process
        if "</body>" in modified_html:
            modified_html = modified_html.replace(
                "</body>",
                "<img src=\"https://i.ibb.co/8L9RQ6pB/Thanks.png\" alt=\"Cover Image\" style=\"width: 100%; height: 100vh; object-fit: cover; break-after: page; display: none;\" onload=\"this.style.display='none'; window.matchMedia('print').addListener(mql => mql.matches &amp;&amp; (this.style.display='block')); window.onafterprint = () => this.style.display='none';\"></body>"
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
#Extract Resources Utilzation from Kibana and analyze it with GPT
def convert_to_iso_format(date_str):
    """Convert '5/11/25, 2:22 PM' format to '2025-05-11T14:22:00.000Z' after subtracting 3 hours"""
    try:
        # Parse the input string (assuming format like '5/11/25, 2:22 PM')
        dt = datetime.strptime(date_str, '%m/%d/%y, %I:%M %p')

        # Subtract 3 hours from the parsed datetime
        dt = dt - timedelta(hours=3)

        # Format to ISO and add milliseconds and Zulu timezone
        return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    except ValueError as e:
        raise ValueError(f"Invalid date format. Expected 'MM/DD/YY, HH:MM AM/PM'. Error: {e}")
def fetch_kibana_metrics_with_login(username, password, service_name, range_from, range_to):
    """
    Fetches Kibana metrics for a specific service after authenticating

    Args:
        username (str): Kibana login username
        password (str): Kibana login password
        service_name (str): The service name to fetch metrics for (e.g., 'Faseh-API')
        range_from (str): Start time in format '5/11/25, 2:22 PM' (will be converted to 3 hours earlier)
        range_to (str): End time in format '5/11/25, 2:22 PM' (will be converted to 3 hours earlier)
    """
    # Convert time formats (subtracting 3 hours)
    try:
        print(f"Original range_from: {range_from}")
        iso_range_from = convert_to_iso_format(range_from)
        print(f"Adjusted ISO range_from: {iso_range_from}")

        print(f"Original range_to: {range_to}")
        iso_range_to = convert_to_iso_format(range_to)
        print(f"Adjusted ISO range_to: {iso_range_to}")
    except ValueError as e:
        print(f"Date conversion error: {e}")
        return None

    # Create a session to maintain cookies between requests
    session = requests.Session()

    # Initial cookies (before login)
    initial_cookies = {
        "_ga": "GA1.1.521425637.1740653592",
        "_ga_0J728DHV7T": "GS1.1.1741257251.3.1.1741257834.0.0.0"
    }

    # Common headers
    common_headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0",
        "kbn-build-number": "80930",
        "kbn-version": "8.17.4",
        "sec-ch-ua": '"Microsoft Edge";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "x-elastic-internal-origin": "Kibana"
    }

    # 1. First make the login request
    login_url = "https://kibana-pp.thiqah.sa:5601/internal/security/login"

    login_headers = common_headers.copy()
    login_headers.update({
        "Origin": "https://kibana-pp.thiqah.sa:5601",
        "Referer": "https://kibana-pp.thiqah.sa:5601/login?msg=LOGGED_OUT",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "x-kbn-context": unquote(
            "%7B%22type%22%3A%22application%22%2C%22name%22%3A%22security_login%22%2C%22url%22%3A%22%2Flogin%22%7D")
    })

    login_payload = {
        "providerType": "basic",
        "providerName": "basic1",
        "currentURL": "https://kibana-pp.thiqah.sa:5601/login?msg=LOGGED_OUT",
        "params": {
            "username": username,
            "password": password
        }
    }

    try:
        # Perform login
        login_response = session.post(
            login_url,
            headers=login_headers,
            cookies=initial_cookies,
            json=login_payload,
            verify=False  # Disabling SSL verification - use with caution!
        )

        login_response.raise_for_status()

        # 2. Now make the metrics request with the authenticated session
        metrics_url = f"https://kibana-pp.thiqah.sa:5601/internal/apm/services/{service_name}/metrics/charts"

        metrics_params = {
            "environment": "ENVIRONMENT_ALL",
            "kuery": "",
            "start": iso_range_from,
            "end": iso_range_to,
            "agentName": "dotnet"
        }

        metrics_headers = common_headers.copy()
        metrics_headers.update({
            "Referer": f"https://kibana-pp.thiqah.sa:5601/app/apm/services/{service_name}/metrics?comparisonEnabled=true&environment=ENVIRONMENT_ALL&kuery=&latencyAggregationType=avg&offset=1d&rangeFrom={iso_range_from}&rangeTo={iso_range_to}&serviceGroup=&transactionType=request",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "x-kbn-context": unquote(
                "%7B%22type%22%3A%22application%22%2C%22name%22%3A%22apm%22%2C%22url%22%3A%22%2Fapp%2Fapm%2Fservices%2F") +
                             service_name +
                             unquote("%2Fmetrics%22%2C%22page%22%3A%22%2Fservices%2F%3AserviceName%2Fmetrics%22%7D")
        })

        metrics_response = session.get(
            metrics_url,
            params=metrics_params,
            headers=metrics_headers,
            verify=False  # Disabling SSL verification - use with caution!
        )

        metrics_response.raise_for_status()
        print("Metrics response:")
        print(metrics_response.json())
        return metrics_response.json()  # Return the parsed JSON response

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None
    finally:
        session.close()



def extract_datetime_from_html(html_file_path, Time):
    """
    Extracts the datetime string from an HTML file with the given structure.
    
    Args:
        html_file_path (str): Path to the HTML file
        Time (str): The text to look for (e.g., "Start Time" or "End Time")
        
    Returns:
        str: The extracted datetime string (e.g., "5/11/25, 2:22 PM")
        or None if not found
    """
    try:
        logging.info(f"Extracting {Time} from {html_file_path}")
        
        with open(html_file_path, 'r', encoding='utf-8') as file:
            html_content = file.read()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find the table row containing the time label
            start_time_row = soup.find('td', string=Time)
            
            if start_time_row and start_time_row.parent:
                # Get the next td which contains our datetime
                datetime_td = start_time_row.parent.find_all('td')[1]
                if datetime_td:
                    # Extract text and remove surrounding quotes if present
                    datetime_str = datetime_td.get_text(strip=True).strip('"')
                    logging.info(f"Found {Time}: {datetime_str}")
                    return datetime_str
            
            # If not found, try to find the start/end time in another way
            # The default JMeter report has a table with Start/End times
            all_tds = soup.find_all('td')
            for td in all_tds:
                if td.get_text().strip() == Time:
                    next_td = td.find_next('td')
                    if next_td:
                        datetime_str = next_td.get_text().strip().strip('"')
                        logging.info(f"Found {Time} (alternative method): {datetime_str}")
                        return datetime_str
            
            logging.warning(f"Could not find {Time} in HTML file")
            # If we can't find the time, return a default time (current time)
            now = datetime.now()
            return now.strftime("%m/%d/%y, %I:%M %p")
        
    except Exception as e:
        logging.error(f"Error extracting datetime: {str(e)}")
        # Return current time as fallback
        now = datetime.now()
        return now.strftime("%m/%d/%y, %I:%M %p")


def ask_gpt_for_CPU_Memory(form_data, html_file_path):
    try:
        logging.info(f"Starting Kibana APM analysis for service: {form_data.get('APM_service_name', 'N/A')}")
        
        # Extract start and end times from the HTML file
        start_time = extract_datetime_from_html(html_file_path, "Start Time")
        end_time = extract_datetime_from_html(html_file_path, "End Time")
        
        logging.info(f"Extracted times - Start: {start_time}, End: {end_time}")
        
        if not start_time or not end_time:
            logging.error("Failed to extract start or end time from HTML file")
            return "No Data found on Kibana APM for provided service name & test duration - Could not extract test time period."
        
        # Fetch metrics from Kibana
        kibana_response = fetch_kibana_metrics_with_login(
            username="mmbakr",
            password="Iamlegand11@",
            service_name=form_data['APM_service_name'],
            range_from=start_time,
            range_to=end_time
        )
        
        if not kibana_response:
            logging.error("Failed to get response from Kibana API")
            return "No Data found on Kibana APM for provided service name & test duration - Failed to connect to Kibana."
        
        logging.info("Successfully received Kibana metrics, sending to GPT for analysis")
        
        # Send to GPT for analysis
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_completion_tokens=100000,
            messages=[
                {"role": "system",
                "content": "You are a data extraction and analysis specialist for performance metrics"},
                {"role": "user",
                "content": "Given the following JSON response, extract only the statistics for:\n\n"
                            "- \"CPU Usage (System max)\"\n"
                            "- \"CPU Usage (Process max)\"\n"
                            "- \"System Memory Usage (Max)\"\n\n"
                            "For each, return:\n"
                            "1. Min value in percentage and the exact UTC time it occurred\n"
                            "2. Max value in percentage and the exact UTC time it occurred\n"
                            "3. Average value in percentage\n"
                            "4. A short analysis of whether the utilization is considered good, moderate, or high, based on the average and max values.\n\n"
                            "Format the output exactly like this:\n\n"
                            "CPU Usage (System max)\n"
                            "Min: [min]% at [min time]\n"
                            "Max: [max]% at [max time]\n"
                            "Average: [average]%\n"
                            "Analysis: [your interpretation of the CPU usage]\n\n"
                            "System Memory Usage (Max)\n"
                            "Min: [min]% at [min time]\n"
                            "Max: [max]% at [max time]\n"
                            "Average: [average]%\n"
                            "Analysis: [your interpretation of the memory usage]\n\n"
                            "(If JSON input doesn't have graphs data, respond with: \"No Data found on Kibana APM for provided service name & test duration\")\n\n"
                            f"Here's the JSON: {kibana_response}"
                }
            ]
        )

        content = response.choices[0].message.content
        logging.info(f"GPT analysis received: {content[:100]}...")
        return content
    except Exception as e:
        logging.error(f"Error in ask_gpt_for_CPU_Memory: {str(e)}")
        return f"No Data found on Kibana APM - Error occurred: {str(e)}"
