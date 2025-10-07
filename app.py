import json
import os
import logging
import uuid

from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify, send_file, \
    session
from werkzeug.utils import secure_filename
from config import Config
from utils.report_utils import generate_jmeter_report
from utils.correlation_utils import analyze_jmeter_correlations, generate_correlated_jmx_with_claude, \
    generate_correlated_jmx_with_openai
from utils.postman_utils import analyze_postman_collection, convert_postman_to_jmx, ask_claude_for_jmx, ask_openai_for_jmx
from utils.har_utils import (
    extract_base_urls,
    extract_methods,
    extract_path_extensions,
    har_to_jmeter_xml,
    har_to_jmeter_jmx
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USAGE_STATS_FILE = os.path.join(os.path.dirname(__file__), 'usage_stats.json')
USAGE_KEYS = [
    'report_generator',
    'correlations_analysis',
    'correlations_jmx_claude',
    'correlations_jmx_openai',
    'postman_analysis',
    'postman_convert_basic',
    'postman_convert_ai_claude',
    'postman_convert_ai_openai',
    'har_convert_recording_xml',
    'har_convert_test_plan_jmx'
]

def _load_usage_stats():
    if not os.path.exists(USAGE_STATS_FILE):
        return {k: 0 for k in USAGE_KEYS}
    try:
        with open(USAGE_STATS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Ensure all keys exist
        for k in USAGE_KEYS:
            data.setdefault(k, 0)
        return data
    except Exception:
        return {k: 0 for k in USAGE_KEYS}

def _save_usage_stats(stats):
    try:
        with open(USAGE_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to save usage stats: {e}")

def increment_usage(key):
    stats = _load_usage_stats()
    stats[key] = stats.get(key, 0) + 1
    _save_usage_stats(stats)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    config_class.init_app(app)

    @app.route('/')
    def index():
        usage_stats = _load_usage_stats()
        return render_template('index.html', usage_stats=usage_stats)

    @app.route('/report-generator', methods=['GET', 'POST'])
    def report_generator():
        if request.method == 'POST':
            try:
                form_data = {
                    'project_name': request.form.get('project_name'),
                    'engineer_name': request.form.get('engineer_name'),
                    'test_round': request.form.get('test_round'),
                    'test_type': request.form.get('performance_test_type'),
                    'cu': request.form.get('cu'),
                    'ramp_up': request.form.get('ramp_up'),
                    'duration': request.form.get('duration'),
                    'url': request.form.get('url'),
                    'round_status': request.form.get('round_status'),
                    'web_trans_status': request.form.get('web_trans_status'),
                    'api_trans_status': request.form.get('api_trans_status'),
                    'error_rate_status': request.form.get('error_rate_status'),
                    'api_threshold': request.form.get('api_threshold'),
                    'err_rate_threshold': request.form.get('err_rate_threshold'),
                    'new_bugs': request.form.get('new_bugs'),
                    'reopened_bugs': request.form.get('reopened_bugs'),
                    'release_report': request.form.get('release_report'),
                    'scope': request.form.get('scope'),
                    'findings_text': request.form.get('findings_text'),
                    'use_gpt': request.form.get('use_gpt') == 'on',
                    'use_kibana_analysis': request.form.get('use_kibana_analysis') == 'on',
                    'APM_service_name': request.form.get('APM_service_name'),
                    'chaos_experiments_count': request.form.get('chaos_experiments_count')
                }

                # Collect dynamic chaos experiment fields based on count
                try:
                    chaos_count = int(form_data.get('chaos_experiments_count') or 0)
                except ValueError:
                    chaos_count = 0
                if chaos_count > 0:
                    for i in range(1, chaos_count + 1):
                        form_data[f'chaos_experiment_{i}_title'] = request.form.get(f'chaos_experiment_{i}_title')
                        form_data[f'chaos_experiment_{i}_status'] = request.form.get(f'chaos_experiment_{i}_status')
                        form_data[f'chaos_experiment_{i}_description'] = request.form.get(f'chaos_experiment_{i}_description')

                if 'report_folder' not in request.files:
                    flash('No report folder selected', 'error')
                    return redirect(request.url)

                report_folder = request.files['report_folder']
                if report_folder.filename == '':
                    flash('No selected file', 'error')
                    return redirect(request.url)

                filename = secure_filename(report_folder.filename)
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                report_folder.save(upload_path)

                result_path = generate_jmeter_report(upload_path, form_data)
                increment_usage('report_generator')

                return send_from_directory(
                    os.path.dirname(result_path),
                    os.path.basename(result_path),
                    as_attachment=True
                )

            except Exception as e:
                logger.error(f"Error generating report: {str(e)}")
                flash(f'Error generating report: {str(e)}', 'error')
                return redirect(request.url)

        return render_template('report_generator.html')

    @app.route('/correlations', methods=['GET', 'POST'])
    def correlations():
        if request.method == 'POST':
            try:
                if 'jmeter_file' not in request.files:
                    flash('No file uploaded', 'error')
                    return redirect(request.url)

                file = request.files['jmeter_file']
                if file.filename == '':
                    flash('No file selected', 'error')
                    return redirect(request.url)

                if not file.filename.endswith('.xml'):
                    flash('Please upload an XML file', 'error')
                    return redirect(request.url)

                filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
                file.save(filepath)

                url_filter = request.form.get('url_filter', '')
                results = analyze_jmeter_correlations(filepath, url_filter)
                increment_usage('correlations_analysis')

                if request.form.get('use_claude') == 'on' and results:
                    try:
                        jmx_path = generate_correlated_jmx_with_claude(results, filepath)
                        increment_usage('correlations_jmx_claude')
                        return send_file(
                            jmx_path,
                            as_attachment=True,
                            download_name=f"claudeai_test_plan_{uuid.uuid4().hex[:8]}.jmx",
                            mimetype='application/xml'
                        )
                    except Exception as e:
                        app.logger.error(f"Error generating JMX with Claude: {str(e)}")
                        flash('Error generating JMX file. Please try again.', 'error')

                if request.form.get('use_openai') == 'on' and results:
                    try:
                        jmx_path = generate_correlated_jmx_with_openai(results, filepath)
                        increment_usage('correlations_jmx_openai')
                        return send_file(
                            jmx_path,
                            as_attachment=True,
                            download_name=f"openai_test_plan_{uuid.uuid4().hex[:8]}.jmx",
                            mimetype='application/xml'
                        )
                    except Exception as e:
                        app.logger.error(f"Error generating JMX with OpenAI: {str(e)}")
                        flash('Error generating JMX file. Please try again.', 'error')

                return render_template('correlations.html', 
                                    results=results, 
                                    show_results=True)

            except Exception as e:
                app.logger.error(f"Error processing file: {str(e)}")
                flash(f'Error processing file: {str(e)}', 'error')
                return redirect(request.url)

        return render_template('correlations.html', show_results=False)

    @app.route('/postman-tools', methods=['GET', 'POST'])
    def postman_tools():
        if request.method == 'POST':
            try:
                if 'postman_file' not in request.files:
                    flash('No file selected', 'error')
                    return redirect(request.url)

                postman_file = request.files['postman_file']
                if postman_file.filename == '':
                    flash('No selected file', 'error')
                    return redirect(request.url)

                filename = secure_filename(postman_file.filename)
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                postman_file.save(upload_path)

                action = request.form.get('action')

                if action == 'analyze':
                    analysis = analyze_postman_collection(upload_path)
                    increment_usage('postman_analysis')
                    session['analyzed_file'] = filename
                    return render_template('postman.html',
                                           analysis=analysis,
                                           show_analysis=True,
                                           analyzed_file=filename)

                elif action == 'convert':
                    use_gpt = request.form.get('enable_gpt') == 'on'
                    if use_gpt:
                        with open(upload_path, 'r', encoding='utf-8') as f:
                            postman_json = json.load(f)
                        correlation_data = analyze_postman_collection(upload_path)
                        output_path = ask_claude_for_jmx(postman_json, correlation_data)
                        increment_usage('postman_convert_ai_claude')
                    else:
                        output_path = convert_postman_to_jmx(upload_path)
                        increment_usage('postman_convert_basic')

                    return send_from_directory(
                        os.path.dirname(output_path),
                        os.path.basename(output_path),
                        as_attachment=True
                    )

            except Exception as e:
                logger.error(f"Error processing Postman collection: {str(e)}")
                flash(f'Error processing Postman collection: {str(e)}', 'error')
                return redirect(request.url)

        return render_template('postman.html', show_analysis=False)

    @app.route('/generate_jmx_with_openai', methods=['POST'])
    def generate_jmx_with_openai():
        if 'analyzed_file' not in session:
            return jsonify({"error": "No analyzed file found. Please analyze the collection first."}), 400
        filename = session['analyzed_file']
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            if not os.path.exists(upload_path):
                return jsonify({"error": "Analyzed file no longer available. Please upload again."}), 400
            with open(upload_path, 'r', encoding='utf-8') as f:
                postman_json = json.load(f)
            correlation_data = analyze_postman_collection(upload_path)
            jmx_path = ask_openai_for_jmx(postman_json, correlation_data)
            increment_usage('postman_convert_ai_openai')
            return send_file(
                jmx_path,
                as_attachment=True,
                download_name=f"openai_{filename.replace('.json', '.jmx')}",
                mimetype='application/xml'
            )
        except Exception as e:
            app.logger.error(f"Error in JMX generation: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/generate_jmx_with_claude', methods=['POST'])
    def generate_jmx_with_claude():
        if 'analyzed_file' not in session:
            return jsonify({"error": "No analyzed file found. Please analyze the collection first."}), 400
        filename = session['analyzed_file']
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            if not os.path.exists(upload_path):
                return jsonify({"error": "Analyzed file no longer available. Please upload again."}), 400
            with open(upload_path, 'r', encoding='utf-8') as f:
                postman_json = json.load(f)
            correlation_data = analyze_postman_collection(upload_path)
            jmx_path = ask_claude_for_jmx(postman_json, correlation_data)
            increment_usage('postman_convert_ai_claude')
            return send_file(
                jmx_path,
                as_attachment=True,
                download_name=f"claude_{filename.replace('.json', '.jmx')}",
                mimetype='application/xml'
            )
        except Exception as e:
            app.logger.error(f"Error in JMX generation: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/har-to-jmeter', methods=['GET', 'POST'])
    def har_to_jmeter():
        uploaded_file = session.get('har_uploaded_file')
        extracted = None
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'upload':
                if 'har_file' not in request.files:
                    flash('No HAR file part', 'error')
                    return redirect(request.url)
                har_file = request.files['har_file']
                if har_file.filename == '':
                    flash('No file selected', 'error')
                    return redirect(request.url)
                if not har_file.filename.lower().endswith('.har'):
                    flash('Please upload a .har file', 'error')
                    return redirect(request.url)
                filename = secure_filename(har_file.filename)
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                har_file.save(save_path)
                session['har_uploaded_file'] = filename
                try:
                    base_urls = extract_base_urls(save_path)
                    methods = extract_methods(save_path)
                    extensions = extract_path_extensions(save_path)
                    extracted = {
                        'base_urls': base_urls,
                        'methods': methods,
                        'extensions': extensions
                    }
                except Exception as e:
                    app.logger.error(f"Error extracting HAR metadata: {e}")
                    flash('Failed to parse HAR file', 'error')
            elif action in ('convert_xml', 'convert_jmx'):
                if not uploaded_file:
                    flash('No HAR file uploaded yet', 'error')
                    return redirect(url_for('har_to_jmeter'))
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], uploaded_file)
                if not os.path.exists(save_path):
                    flash('Uploaded HAR file missing. Upload again.', 'error')
                    session.pop('har_uploaded_file', None)
                    return redirect(url_for('har_to_jmeter'))
                # Gather selections
                selected_urls = request.form.getlist('selected_urls') or None
                selected_methods = request.form.getlist('selected_methods') or None
                # IMPORTANT: Do NOT collapse an empty extensions selection to None; empty list means user unchecked all
                selected_extensions = request.form.getlist('selected_extensions')
                group_txn = request.form.get('group_txn') == 'on'
                base_name = os.path.splitext(uploaded_file)[0]
                if action == 'convert_xml':
                    out_name = f"{base_name}_recording.xml"
                    out_path = os.path.join(app.config['UPLOAD_FOLDER'], out_name)
                    success, message = har_to_jmeter_xml(
                        save_path,
                        out_path,
                        selected_urls,
                        selected_methods,
                        selected_extensions,
                        status_callback=None
                    )
                    if success:
                        increment_usage('har_convert_recording_xml')
                        return send_file(out_path, as_attachment=True, download_name=out_name, mimetype='application/xml')
                    else:
                        flash(message, 'error')
                else:  # convert_jmx
                    out_name = f"{base_name}.jmx"
                    out_path = os.path.join(app.config['UPLOAD_FOLDER'], out_name)
                    success, message = har_to_jmeter_jmx(
                        save_path,
                        out_path,
                        selected_urls,
                        selected_methods,
                        selected_extensions,
                        status_callback=None,
                        use_transaction_controllers=group_txn
                    )
                    if success:
                        increment_usage('har_convert_test_plan_jmx')
                        return send_file(out_path, as_attachment=True, download_name=out_name, mimetype='application/xml')
                    else:
                        flash(message, 'error')
                # Rebuild extracted lists for redisplay
                try:
                    base_urls = extract_base_urls(save_path)
                    methods = extract_methods(save_path)
                    extensions = extract_path_extensions(save_path)
                    extracted = {
                        'base_urls': base_urls,
                        'methods': methods,
                        'extensions': extensions,
                        'selected_urls': selected_urls or [],
                        'selected_methods': selected_methods or [],
                        'selected_extensions': selected_extensions or [],
                        'group_txn': group_txn
                    }
                except Exception:
                    pass
        return render_template('har_converter.html', extracted=extracted, uploaded_file=uploaded_file)

    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(os.path.join(app.root_path, 'static'),
                                  'images/favicon.ico', mimetype='image/vnd.microsoft.icon')

    @app.route('/features')
    def features():
        return render_template('features.html')

    @app.errorhandler(413)
    def request_entity_too_large(error):
        return render_template('error.html', message='File too large (max 16MB)'), 413

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('error.html', message='Page not found'), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('error.html', message='Internal server error'), 500

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=True)