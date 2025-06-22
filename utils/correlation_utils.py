import re
import json
import logging
from lxml import etree as ET
import anthropic
import os
import uuid
import urllib.parse  # Add for URL encoding/decoding
from flask import current_app
from openai import OpenAI

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, OPENAI_API_KEY, OPENAI_MODEL
import openai


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


def get_encoding_variations(value):
    """
    Generate variations of the value with different URL encoding/decoding
    to help match parameters across requests/responses
    """
    variations = set([value])  # Start with original value
    
    try:
        # Try to decode as URL-encoded string
        decoded = urllib.parse.unquote(value)
        if decoded != value:
            variations.add(decoded)
        
        # Try to encode as URL-encoded string
        encoded = urllib.parse.quote(value)
        if encoded != value:
            variations.add(encoded)
            
        # Special handling for base64 strings that often end with '=' and get encoded as %3D
        if value.endswith('=='):
            variations.add(value.replace('==', '%3D%3D'))
        elif value.endswith('='):
            variations.add(value.replace('=', '%3D'))
        elif value.endswith('%3D%3D'):
            variations.add(value.replace('%3D%3D', '=='))
        elif value.endswith('%3D'):
            variations.add(value.replace('%3D', '='))
    except Exception as e:
        # If any encoding/decoding errors occur, just use the original value
        current_app.logger.debug(f"Encoding variation error for '{value}': {str(e)}")
    
    return list(variations)


def extract_params(text):
    params = {}
    if not text:
        return params

    # First try to parse as query string parameters
    pairs = re.findall(r'([\w\.-]+)=([^&]*)', text)
    if pairs:
        for key, value in pairs:
            # URL-decode the value
            try:
                decoded_value = urllib.parse.unquote(value)
                params[key] = decoded_value
            except:
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
    if not filters:
        return True
        
    normalized_request = normalize_url(request_url)
    for filter_val in filters:
        normalized_filter = normalize_url(filter_val)
        if not normalized_filter:  # Empty filter means match all
            return True
        if normalized_filter in normalized_request:
            return True
    return False


def analyze_jmeter_correlations(xml_path, url_filter=''):
    requests = []
    responses = []
    all_previous_responses = []
    skipped_samples = 0
    total_samples = 0
    processed_labels = set()  # Track which labels we've processed

    def collect_samples(node):
        nonlocal skipped_samples, total_samples
        
        # Enhanced sample node detection logic
        is_sample = False
        tag_name = ""
        if node.tag is not None:
            tag_name = node.tag.split('}')[-1] if '}' in node.tag else node.tag
            is_sample = (
                tag_name.endswith('Sample') or 
                tag_name == 'sample' or 
                tag_name == 'httpSample' or
                'httpsample' in tag_name.lower() or
                'HTTPSampler' in tag_name
            )
        
        if is_sample:
            total_samples += 1
            
            # More robust URL extraction with multiple fallbacks
            url = None
            # Try all possible locations for URL
            for url_path in ['java.net.URL', 'URL', 'url', './/java.net.URL', './/URL', './/url']:
                try:
                    url_elem = node.find(url_path)
                    if url_elem is not None and url_elem.text:
                        url = url_elem.text
                        break
                    
                    # Try as a direct text element
                    url_text = node.findtext(url_path)
                    if url_text:
                        url = url_text
                        break
                except:
                    continue
                
            # Also check for samplerData which may contain the URL for OPTIONS requests
            if not url:
                sampler_data = node.findtext('samplerData') or ''
                if sampler_data:
                    url_match = re.search(r'(https?://[^\s]+)', sampler_data)
                    if url_match:
                        url = url_match.group(1)
            
            # Skip if no URL found
            if not url:
                skipped_samples += 1
                label = node.get('lb') or 'No_Label'
                method = node.findtext('method') or node.get('mc', 'UNKNOWN')
                current_app.logger.debug(f"Skipping sample without URL: Label={label}, Method={method}")
                
                # Try to extract any data available for debugging
                for elem in node:
                    if elem.tag:
                        tag = elem.tag.split('}')[-1]
                        current_app.logger.debug(f"  Available data: {tag}={elem.text}")
            else:
                request_body = node.findtext('queryString') or ''
                method = node.findtext('method') or node.get('mc', '')
                request_header = node.findtext('requestHeader') or ''
                label = node.get('lb') or 'No_Label'
                
                # Track if we've already processed a similar request to avoid duplicates
                processed_labels.add(label)

                # Better handling of response data
                response_header = node.findtext('responseHeader') or ''
                response_body = node.findtext('responseData') or ''
                
                # Handle non-text response data
                if not response_body or 'Non-TEXT response data' in response_body:
                    response_body = f"[Binary data: {label}]"
                    current_app.logger.debug(f"Binary response detected for {label}, URL: {url}")
                
                # Build request and response objects
                requests.append({
                    'url': url,
                    'method': method,
                    'requestHeader': request_header,
                    'requestBody': request_body,
                    'label': label,
                    'raw_node': node  # Store reference to original node for debugging
                })
                
                responses.append({
                    'responseHeader': response_header,
                    'responseBody': response_body,
                    'full_response': response_header + '\n' + response_body,
                })

        # Process all child nodes recursively
        for child in node:
            collect_samples(child)

    try:
        root = clean_and_parse_xml(xml_path)
    except Exception as e:
        raise RuntimeError(f"Failed to parse cleaned XML: {e}")

    collect_samples(root)
    
    # Enhanced logging
    current_app.logger.info(f"Collected {len(requests)}/{total_samples} requests from XML. Skipped: {skipped_samples}")
    current_app.logger.info(f"Processed labels: {', '.join(sorted(processed_labels))}")

    url_filters = [u.strip() for u in url_filter.split(',')] if url_filter else []

    results = []
    for idx, req in enumerate(requests):
        # Skip invalid requests
        if not req['url']:
            continue
            
        # Improved URL filter logic
        if url_filters and not url_matches_filter(req['url'], url_filters):
            current_app.logger.debug(f"Filtered out URL: {req['url']}")
            continue

        # Extract parameters from both URL and request body
        url_query = ''
        if req['url'] and '?' in req['url']:
            parts = req['url'].split('?', 1)
            if len(parts) > 1:
                url_query = parts[1]
                
        params = extract_params(url_query)
        body_params = extract_params(req['requestBody'])
        params.update(body_params)

        # Try to extract parameters from headers for more coverage
        if not params and req['requestHeader']:
            content_type = ""
            for line in req['requestHeader'].splitlines():
                if "Content-Type:" in line:
                    content_type = line.split(":", 1)[1].strip()
            
            # If it's a form submission, try to parse the body differently
            if "application/x-www-form-urlencoded" in content_type:
                body_params = extract_params(req['requestBody'])
                params.update(body_params)

        if not params:
            current_app.logger.debug(f"No parameters found for request: {req['label']}, URL: {req['url']}")
            # Include parameterless requests in results anyway
            results.append({
                'label': req['label'],
                'method': req['method'],
                'url': req['url'],
                'params': []
            })
            continue

        param_details = []
        for param_name, param_value in params.items():
            if not param_value:
                continue

            # Generate variations of the parameter value with different encodings
            param_variations = get_encoding_variations(param_value)
            
            # Find all previous responses that contain this parameter value or its variations
            matching_responses = []
            for resp_idx, resp in enumerate(responses[:idx]):
                if not resp['full_response']:
                    continue
                    
                matched = False
                best_match = None
                
                # Try each variation of the parameter value
                for variation in param_variations:
                    if variation in resp['full_response']:
                        matches = extract_dynamic_patterns(resp['full_response'], variation)
                        if matches:
                            matched = True
                            best_match = {
                                'index': resp_idx,
                                'label': requests[resp_idx]['label'],
                                'matches': matches[:3],  # Limit to first 3 matches
                                'matched_variation': variation
                            }
                            break
                
                if matched and best_match:
                    matching_responses.append(best_match)

            if matching_responses:
                first_match = matching_responses[0]
                last_match = matching_responses[-1]

                param_details.append({
                    'param': param_name,
                    'value': param_value,
                    'correlated': True,
                    'encoding_note': 'URL encoding variation detected' if first_match.get('matched_variation') != param_value else None,
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

        results.append({
            'label': req['label'],
            'method': req['method'],
            'url': req['url'],
            'params': param_details
        })

    current_app.logger.info(f"Final number of requests with parameters: {len(results)}")
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
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

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
            "Please return only the JMeter JMX XML content."
        )

        # Stream response from Claude
        with client.messages.stream(
            model=ANTHROPIC_MODEL,
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


def generate_correlated_jmx_with_openai(correlation_results, xml_path):
    """Generate a JMX file with correlated requests using OpenAI."""
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        # client = OpenAI(
        #               base_url="https://openrouter.ai/api/v1",
        #               api_key="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",
        #             )

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
                        'value': p['value'],
                        'pattern': p['first_source']['matches'][0] if p['first_source']['matches'] else None,
                        'source_label': p['first_source']['label']
                    } for p in correlated_params]
                })

        prompt = (
            "You are a senior performance test engineer specializing in JMeter test design. "
            "Create a complete JMeter JMX test plan based on the provided HTTP samples and correlation requirements.\n\n"
            "Requirements:\n"
            "1. Generate a properly structured JMeter test plan with ThreadGroup and all necessary HTTP requests\n"
            "2. Implement JSON/RegEx extractors for all identified correlations\n"
            "3. Replace all dynamic parameters with JMeter variables using the proper syntax\n"
            "4. Add appropriate assertions and listeners for performance testing\n"
            "5. Ensure the output is valid JMX XML that can be directly imported into JMeter without modifications\n\n"
            "=== HTTP Samples ===\n"
            f"{json.dumps(summarized_samples, indent=2)}\n\n"
            "=== Correlation Requirements ===\n"
            f"{json.dumps(requests_info, indent=2)}\n\n"
            "Respond with ONLY the complete, valid JMeter JMX XML content. Include all necessary XML declarations "
            "and JMeter components."
        )

        # Get response from OpenAI
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            # model="deepseek/deepseek-r1:free",
            messages=[
                {"role": "system", "content": "You are a performance test engineer specializing in JMeter test plans. Return only valid JMX XML content."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=100000,
        )
        print(response.choices[0].message.content)
        jmx_content = extract_jmx_xml(response.choices[0].message.content)

        if jmx_content.strip():
            output_path = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                f"openai_test_plan_{uuid.uuid4().hex[:8]}.jmx"
            )
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(jmx_content)
            return output_path
        else:
            raise ValueError("OpenAI returned no valid JMX content")

    except Exception as e:
        current_app.logger.error(f"Error generating JMX with OpenAI: {str(e)}")
        raise


def extract_jmx_xml(text):
    """Extract JMX XML content from Claude's response"""
    # Look for XML content between tags or code blocks
    xml_pattern = r'(?s)(?:<\?xml.*?</jmeterTestPlan>)|(?:```xml\n(.*?)\n```)'
    match = re.search(xml_pattern, text)
    if match:
        return match.group(1) if match.group(1) else match.group(0)
    return ""