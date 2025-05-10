import re
import json
from lxml import etree as ET
import os


def analyze_jmeter_correlations(xml_path, url_filter=''):
    """Analyze JMeter XML for correlations"""
    requests = []
    responses = []
    all_previous_responses = []

    def collect_samples(node):
        if node.tag.endswith('httpSample') or node.tag.endswith('sample'):
            url = node.findtext('java.net.URL')
            request_body = node.findtext('queryString') or ''
            method = node.findtext('method') or ''
            request_header = node.findtext('requestHeader') or ''
            label = node.get('lb') or 'No_Label'

            response_header = node.findtext('responseHeader') or ''
            response_body = node.findtext('responseData') or ''

            if url:
                requests.append({
                    'url': url,
                    'method': method,
                    'requestHeader': request_header,
                    'requestBody': request_body,
                    'label': label,
                })
                responses.append({
                    'responseHeader': response_header,
                    'responseBody': response_body,
                })

        for child in node:
            collect_samples(child)

    def extract_params(text):
        params = {}
        if not text:
            return params
        pairs = re.findall(r'([\w\.-]+)=([^&]*)', text)
        if pairs:
            for key, value in pairs:
                params[key] = value
            return params
        try:
            json_data = json.loads(text)
            params.update(flatten_json(json_data))
        except Exception:
            pass
        return params

    def flatten_json(y, parent_key='', sep='.'):
        items = {}
        if isinstance(y, dict):
            for k, v in y.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, (dict, list)):
                    items.update(flatten_json(v, new_key, sep=sep))
                else:
                    items[new_key] = str(v)
        elif isinstance(y, list):
            for i, v in enumerate(y):
                new_key = f"{parent_key}{sep}{i}" if parent_key else str(i)
                if isinstance(v, (dict, list)):
                    items.update(flatten_json(v, new_key, sep=sep))
                else:
                    items[new_key] = str(v)
        return items

    def normalize_url(url):
        return url.replace('https://', '').replace('http://', '').strip().lower()

    def url_matches_filter(request_url, filters):
        normalized_request = normalize_url(request_url)
        for filter_val in filters:
            normalized_filter = normalize_url(filter_val)
            if normalized_filter in normalized_request:
                return True
        return False

    # Parse XML
    tree = ET.parse(xml_path)
    root = tree.getroot()
    collect_samples(root)

    # Prepare all responses
    all_previous_responses = [resp['responseHeader'] + '\n' + resp['responseBody'] for resp in responses]

    # Process URL filters
    url_filters = [u.strip() for u in url_filter.split(',')] if url_filter else []

    # Analyze correlations
    results = []
    for idx, req in enumerate(requests):
        if url_filters and not url_matches_filter(req['url'], url_filters):
            continue

        url_query = req['url'].split('?', 1)[1] if req['url'] and '?' in req['url'] else ''
        params = extract_params(url_query)
        params.update(extract_params(req['requestBody']))

        if not params:
            continue

        param_details = []
        for param_name, param_value in params.items():
            if not param_value:
                continue

            first_found_idx = None
            nearest_found_idx = None

            # Find first occurrence
            for resp_idx in range(0, idx):
                if param_value in all_previous_responses[resp_idx]:
                    first_found_idx = resp_idx
                    break

            # Find nearest occurrence
            for resp_idx in range(idx - 1, -1, -1):
                if param_value in all_previous_responses[resp_idx]:
                    nearest_found_idx = resp_idx
                    break

            if first_found_idx is not None or nearest_found_idx is not None:
                first_label = requests[first_found_idx]['label'] if first_found_idx is not None else 'N/A'
                nearest_label = requests[nearest_found_idx]['label'] if nearest_found_idx is not None else 'N/A'
                param_details.append({
                    'param': param_name,
                    'value': param_value,
                    'correlated': True,
                    'first_source': first_label,
                    'nearest_source': nearest_label
                })
            else:
                param_details.append({
                    'param': param_name,
                    'value': param_value,
                    'correlated': False
                })

        if param_details:
            results.append({
                'label': req['label'],
                'url': req['url'],
                'params': param_details
            })

    return results