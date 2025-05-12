import re
import json
from lxml import etree as ET
import anthropic
import os
import uuid
from flask import current_app


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


def get_filtered_samples(xml_path, correlation_results):
    """Extract relevant HTTP samples from original JMX"""
    root = clean_and_parse_xml(xml_path)
    relevant_labels = {result['label'] for result in correlation_results}
    filtered_samples = []
    
    def collect_relevant_samples(node):
        if node.tag.endswith('httpSample') or node.tag.endswith('sample'):
            label = node.get('lb')
            if label in relevant_labels:
                filtered_samples.append(ET.tostring(node, encoding='unicode', pretty_print=True))
        for child in node:
            collect_relevant_samples(child)
    
    collect_relevant_samples(root)
    return filtered_samples


def summarize_http_sample(xml_str):
    """Summarize HTTP sample XML to reduce tokens while keeping essential information"""
    try:
        node = ET.fromstring(xml_str)
        return {
            'label': node.get('lb', ''),
            'url': node.findtext('java.net.URL', ''),
            'method': node.findtext('method', ''),
            'path': node.findtext('path', ''),
            'query_string': node.findtext('queryString', '')[:100] + '...' if node.findtext('queryString', '') else '',
            'headers': {
                line.split(':', 1)[0]: line.split(':', 1)[1]
                for line in (node.findtext('requestHeader', '').split('\n'))
                if ':' in line
            }
        }
    except Exception:
        return None


def generate_correlated_jmx_with_claude(correlation_results, xml_path):
    """Generate a JMX file with correlated requests using Claude AI."""
    try:
        client = anthropic.Anthropic(
            api_key="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"
        )

        # Get filtered XML samples and summarize them
        original_samples = get_filtered_samples(xml_path, correlation_results)
        summarized_samples = [
            summarize_http_sample(sample) 
            for sample in original_samples
            if sample
        ]
        
        # Prepare correlation data
        requests_info = []
        for result in correlation_results:
            correlated_params = [p for p in result['params'] if p['correlated']]
            if correlated_params:
                requests_info.append({
                    'label': result['label'],
                    'url': result['url'],
                    'method': result['method'],
                    'correlations': [{
                        'param': p['param'],
                        'pattern': p['first_source']['matches'][0] if p['first_source']['matches'] else None,
                        'source_label': p['first_source']['label']
                    } for p in correlated_params]
                })

        prompt = (
            "You are a senior QA automation engineer. Create a complete JMeter JMX test plan "
            "using the summarized requests and correlation information provided below.\n\n"
            f"=== Original HTTP Samples (Summarized) ===\n"
            f"{json.dumps(summarized_samples, indent=2)}\n\n"
            f"=== Correlation Requirements ===\n"
            f"{json.dumps(requests_info, indent=2)}\n\n"
            "Create a JMX file that:\n"
            "1. Creates HTTP requests based on the summarized samples\n"
            "2. Adds Regular Expression Extractors for the correlations\n"
            "3. Updates the correlated parameters to use variables\n"
            "4. Includes proper Thread Group configuration\n"
            "Please return only the JMeter JMX XML content."
        )

        # Stream response from Claude
        with client.messages.stream(
            model="claude-3-7-sonnet-20250219",
            max_tokens=32000,  # Reduced max tokens
            temperature=0.3,
            system="You are a senior QA automation engineer specializing in JMeter test plans.",
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            full_text = ""
            for chunk in stream:
                if chunk.type == "content_block_delta":
                    full_text += chunk.delta.text

            jmx_content = extract_jmx_xml(full_text)

            if jmx_content.strip():
                output_path = os.path.join(
                    current_app.config['UPLOAD_FOLDER'],
                    f"correlated_test_plan_{uuid.uuid4().hex[:8]}.jmx"
                )
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(jmx_content)
                return output_path
            else:
                raise ValueError("Claude returned no valid JMX content")

    except Exception as e:
        current_app.logger.error(f"Error generating JMX with Claude: {str(e)}")
        raise


def extract_jmx_xml(text):
    """Extract JMX XML content from Claude's response"""
    # Look for XML content between tags or code blocks
    xml_pattern = r'(?s)(?:<\?xml.*?</jmeterTestPlan>)|(?:```xml\n(.*?)\n```)'
    match = re.search(xml_pattern, text)
    if match:
        return match.group(1) if match.group(1) else match.group(0)
    return ""