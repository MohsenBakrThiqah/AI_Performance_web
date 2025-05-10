import re
import json
from lxml import etree as ET


def is_valid_xml_char(codepoint):
    return (
        codepoint == 0x9 or
        codepoint == 0xA or
        codepoint == 0xD or
        (0x20 <= codepoint <= 0xD7FF) or
        (0xE000 <= codepoint <= 0xFFFD) or
        (0x10000 <= codepoint <= 0x10FFFF)
    )


def remove_invalid_xml_references(text):
    def replace_entity(match):
        ref = match.group(1)
        try:
            codepoint = int(ref, 16) if ref.lower().startswith('x') else int(ref)
            return '' if not is_valid_xml_char(codepoint) else chr(codepoint)
        except ValueError:
            return ''
    return re.sub(r'&#(x?[0-9A-Fa-f]+);', replace_entity, text)


def clean_and_parse_xml(filepath):
    with open(filepath, 'rb') as f:
        raw = f.read()

    decoded = raw.decode('utf-8', errors='ignore')
    cleaned = remove_invalid_xml_references(decoded)
    return ET.fromstring(cleaned.encode('utf-8'))


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


def normalize_url(url):
    return url.replace('https://', '').replace('http://', '').strip().lower()


def url_matches_filter(request_url, filters):
    normalized_request = normalize_url(request_url)
    for filter_val in filters:
        normalized_filter = normalize_url(filter_val)
        if normalized_filter in normalized_request:
            return True
    return False


def analyze_jmeter_correlations(xml_path, url_filter=''):
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

    try:
        root = clean_and_parse_xml(xml_path)
    except Exception as e:
        raise RuntimeError(f"Failed to parse cleaned XML: {e}")

    collect_samples(root)

    all_previous_responses = [resp['responseHeader'] + '\n' + resp['responseBody'] for resp in responses]

    url_filters = [u.strip() for u in url_filter.split(',')] if url_filter else []

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

            first_found_idx = next((i for i in range(idx) if param_value in all_previous_responses[i]), None)
            nearest_found_idx = next((i for i in range(idx - 1, -1, -1) if param_value in all_previous_responses[i]), None)

            if first_found_idx is not None or nearest_found_idx is not None:
                param_details.append({
                    'param': param_name,
                    'value': param_value,
                    'correlated': True,
                    'first_source': requests[first_found_idx]['label'] if first_found_idx is not None else 'N/A',
                    'nearest_source': requests[nearest_found_idx]['label'] if nearest_found_idx is not None else 'N/A'
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
