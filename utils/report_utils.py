import os
import json
import re
import shutil
import time
import logging
from lxml import etree as ET
import openai
from urllib.parse import urlparse
import html


def generate_jmeter_report(folder_path, form_data):
    """Generate JMeter report from the provided folder and form data"""
    try:
        # Create output directory
        output_dir = os.path.join(os.path.dirname(folder_path), 'generated_report')
        os.makedirs(output_dir, exist_ok=True)

        # Copy original files to output directory
        for item in os.listdir(folder_path):
            src = os.path.join(folder_path, item)
            dst = os.path.join(output_dir, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        # Process files
        html_file_path = os.path.join(output_dir, 'index.html')
        js_file_path = os.path.join(output_dir, 'content/js/dashboard.js')
        statistics_file_path = os.path.join(output_dir, 'statistics.json')

        # Edit HTML and JS files
        edit_html_and_js(html_file_path, js_file_path, statistics_file_path, form_data)

        # Edit statistics table
        edit_statistics_table(js_file_path)

        # Set pass/fail colors
        pass_fail_colors(js_file_path, os.path.join(output_dir, 'content/css/dashboard.css'),
                         form_data['api_threshold'], form_data['err_rate_threshold'])

        return html_file_path

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

        # Add findings
        findings_html = "<br>".join(
            [f"{i + 1}. {finding}" for i, finding in enumerate(form_data['findings']) if finding])
        modified_html = re.sub(
            r'<tr>\s*<td>Findings</td>\s*<td>""</td>\s*</tr>',
            f'<tr><td>Findings</td><td>{findings_html}</td></tr>',
            modified_html
        )

        # GPT analysis if enabled
        if form_data['use_gpt']:
            gpt_response = ask_gpt(statistics_content, form_data)
            modified_html = modified_html.replace(
                '<script src="sbadmin2-1.0.7/bower_components/jquery/dist/jquery.min.js"></script>',
                f'<script src="sbadmin2-1.0.7/bower_components/jquery/dist/jquery.min.js"></script>\n{gpt_response}'
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
                        <td>{form_data['engineer_name']}</td>
                    </tr>
                    <tr>
                        <td>URL Under Test</td>
                        <td>{form_data['url']}</td>
                    </tr>
                    <tr>
                        <td>Test Round</td>
                        <td>{form_data['test_round']}</td>
                    </tr>
                    <!-- More rows for all form data -->
                </table>
    '''


def ask_gpt(statistics_content, form_data):
    """Get analysis from GPT"""
    try:
        prompt = f"""Create a comprehensive analysis with the following Criteria: Thiqah standards
        Accepted pct1ResTime (90% Line): Up to {form_data['api_threshold']} millisecond.
        Accepted errorPct: Up to {form_data['err_rate_threshold']}

        First Section: Summary for the analysis.
        Second section: short summary for requests that have the highest impact for application slowness."""

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a Performance test engineer"},
                {"role": "user", "content": prompt + "\n\nTest data:\n" + statistics_content}
            ]
        )

        analysis = response['choices'][0]['message']['content']
        return f'<div class="gpt-analysis"><h3>GPT Analysis</h3><p>{analysis.replace("\n", "<br>")}</p></div>'

    except Exception as e:
        logging.error(f"Error getting GPT analysis: {str(e)}")
        return "<div>GPT analysis failed</div>"