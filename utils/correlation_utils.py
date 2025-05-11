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


def extract_dynamic_patterns(text, value):
    """Extract patterns using the value as a dynamic regular expression"""
    if not text or not value:
        return []

    # Escape special regex characters in the value
    escaped_value = re.escape(value)
    # Create a pattern that matches the value with some context
    pattern = f"(.{{0,20}}?){escaped_value}(.{{0,20}}?)"

    try:
        matches = re.findall(pattern, text)
        # Replace the actual value with (.+?) in the matches
        processed_matches = [f"{before}(.+?){after}" for before, after in matches]
        return processed_matches
    except Exception:
        return []


def extract_params(text):
    params = {}
    if not text:
        return params

    # First try to parse as query string parameters
    pairs = re.findall(r'([\w\.-]+)=([^&]*)', text)
    if pairs:
        for key, value in pairs:
            params[key] = value
        return params

    # Then try to parse as JSON
    try:
        json_data = json.loads(text)
        if isinstance(json_data, (dict, list)):
            # For JSON objects/arrays, we'll still use flatten_json
            return flatten_json(json_data)
        else:
            # For simple JSON values, store as is
            params['value'] = str(json_data)
            return params
    except json.JSONDecodeError:
        # For non-JSON content, store the raw text if it's not empty
        if text.strip():
            params['raw_content'] = text.strip()
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
                    'full_response': response_header + '\n' + response_body,
                })

        for child in node:
            collect_samples(child)

    try:
        root = clean_and_parse_xml(xml_path)
    except Exception as e:
        raise RuntimeError(f"Failed to parse cleaned XML: {e}")

    collect_samples(root)

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

            # Find all previous responses that contain this parameter value
            matching_responses = []
            for resp_idx, resp in enumerate(responses[:idx]):
                if param_value in resp['full_response']:
                    matches = extract_dynamic_patterns(resp['full_response'], param_value)
                    matching_responses.append({
                        'index': resp_idx,
                        'label': requests[resp_idx]['label'],
                        'matches': matches[:3]  # Limit to first 3 matches
                    })

            if matching_responses:
                first_match = matching_responses[0]
                last_match = matching_responses[-1]

                param_details.append({
                    'param': param_name,
                    'value': param_value,
                    'correlated': True,
                    'first_source': {
                        'label': first_match['label'],
                        'matches': first_match['matches']
                    },
                    'nearest_source': {
                        'label': last_match['label'],
                        'matches': last_match['matches']
                    },
                    'all_matches_count': len(matching_responses)
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
                'method': req['method'],
                'url': req['url'],
                'params': param_details
            })

    return results