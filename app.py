import json
import os
import logging
import uuid

from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify, send_file, \
    session
from werkzeug.utils import secure_filename
from config import Config
from utils.report_utils import generate_jmeter_report
from utils.correlation_utils import analyze_jmeter_correlations
from utils.postman_utils import analyze_postman_collection, convert_postman_to_jmx, ask_claude_for_jmx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    config_class.init_app(app)

    @app.route('/')
    def index():
        return render_template('index.html')

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
                    'finding_1': request.form.get('finding_1'),
                    'finding_2': request.form.get('finding_2'),
                    'finding_3': request.form.get('finding_3'),
                    'finding_4': request.form.get('finding_4'),
                    'finding_5': request.form.get('finding_5'),
                    'finding_6': request.form.get('finding_6'),
                    'finding_7': request.form.get('finding_7'),
                    'finding_8': request.form.get('finding_8'),
                    'finding_9': request.form.get('finding_9'),
                    'finding_10': request.form.get('finding_10'),
                    'finding_11': request.form.get('finding_11'),
                    'finding_12': request.form.get('finding_12'),
                    'use_gpt': request.form.get('use_gpt') == 'on'
                }

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
                    flash('No file selected', 'error')
                    return redirect(request.url)

                jmeter_file = request.files['jmeter_file']
                if jmeter_file.filename == '':
                    flash('No selected file', 'error')
                    return redirect(request.url)

                filename = secure_filename(jmeter_file.filename)
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                jmeter_file.save(upload_path)

                url_filter = request.form.get('url_filter', '')
                results = analyze_jmeter_correlations(upload_path, url_filter)

                return render_template('correlations.html', results=results, show_results=True)

            except Exception as e:
                logger.error(f"Error analyzing correlations: {str(e)}")
                flash(f'Error analyzing correlations: {str(e)}', 'error')
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
                    # Store the filename in session for Claude generation
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
                    else:
                        output_path = convert_postman_to_jmx(upload_path)

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

    @app.route('/generate_jmx_with_claude', methods=['POST'])
    def generate_jmx_with_claude():
        # Get the filename from session that was stored during analysis
        if 'analyzed_file' not in session:
            return jsonify({"error": "No analyzed file found. Please analyze the collection first."}), 400

        filename = session['analyzed_file']
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        try:
            # Verify the file still exists
            if not os.path.exists(upload_path):
                return jsonify({"error": "Analyzed file no longer available. Please upload again."}), 400

            # Analyze the collection for correlations
            with open(upload_path, 'r', encoding='utf-8') as f:
                postman_json = json.load(f)

            correlation_data = analyze_postman_collection(upload_path)

            # Generate JMX with Claude
            jmx_path = ask_claude_for_jmx(postman_json, correlation_data)

            # Return the generated JMX file
            return send_file(
                jmx_path,
                as_attachment=True,
                download_name=f"claude_{filename.replace('.json', '.jmx')}",
                mimetype='application/xml'
            )

        except Exception as e:
            app.logger.error(f"Error in JMX generation: {str(e)}")
            return jsonify({"error": str(e)}), 500

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
    app.run(debug=True)