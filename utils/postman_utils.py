import json
import os
import re
import uuid
import html
from urllib.parse import urlparse
from lxml import etree as ET
import openai
from flask import current_app


def analyze_postman_collection(postman_file_path):
    """Analyze a Postman collection for correlations and parameters"""
    try:
        with open(postman_file_path, 'r', encoding='utf-8') as f:
            collection = json.load(f)

        all_items = []
        walk_items(collection.get('item', []), all_items)

        correlation_summary = []

        for current_index, item in enumerate(all_items):
            if 'request' not in item:
                continue

            name = item.get("name", f"Request {current_index + 1}")
            request = item['request']
            body_json = extract_request_body(request)

            if not body_json:
                continue

            flat_params = flatten_json(body_json)
            param_list = []

            for param, value in flat_params.items():
                if not value:
                    continue

                matched = False
                param_key = param.split('.')[-1]

                # Check previous requests for this value
                for prev_item in all_items[:current_index]:
                    if 'response' not in prev_item:
                        continue

                    for resp in prev_item.get("response", []):
                        try:
                            resp_body = json.loads(resp.get("body", "{}"))
                            jsonpath = find_matching_jsonpath_by_key_and_value(resp_body, param_key, value)
                            if jsonpath:
                                param_list.append({
                                    "param": param,
                                    "value": value,
                                    "correlate": True,
                                    "source": prev_item.get("name", "Unknown"),
                                    "jsonpath": jsonpath
                                })
                                matched = True
                                break
                        except json.JSONDecodeError:
                            continue
                    if matched:
                        break

                if not matched:
                    param_list.append({
                        "param": param,
                        "value": value,
                        "correlate": False
                    })

            if param_list:
                correlation_summary.append({
                    "request": name,
                    "method": request.get("method", "GET"),
                    "url": get_request_url(request),
                    "parameters": param_list
                })

        return {
            "collection_name": collection.get("info", {}).get("name", "Unnamed Collection"),
            "requests": correlation_summary
        }

    except Exception as e:
        current_app.logger.error(f"Error analyzing Postman collection: {str(e)}")
        raise


def convert_postman_to_jmx(postman_file_path):
    """Convert a Postman collection to JMeter JMX format"""
    try:
        with open(postman_file_path, 'r', encoding='utf-8') as f:
            postman_data = json.load(f)

        output_path = os.path.join(
            current_app.config['UPLOAD_FOLDER'],
            f"{clean_name(postman_data.get('info', {}).get('name', 'postman_collection'))}.jmx"
        )

        # Create JMX structure
        root = ET.Element("jmeterTestPlan", version="1.2", properties="5.0", jmeter="5.6.2")
        hash_tree = ET.SubElement(root, "hashTree")

        # Test Plan
        test_plan = ET.SubElement(hash_tree, "TestPlan",
                                  guiclass="TestPlanGui",
                                  testclass="TestPlan",
                                  testname="Postman Import",
                                  enabled="true")
        ET.SubElement(test_plan, "stringProp", name="TestPlan.comments")
        ET.SubElement(test_plan, "boolProp", name="TestPlan.functional_mode").text = "false"
        ET.SubElement(test_plan, "boolProp", name="TestPlan.serialize_threadgroups").text = "false"
        ET.SubElement(test_plan, "elementProp", name="TestPlan.user_defined_variables", elementType="Arguments")
        ET.SubElement(test_plan, "stringProp", name="TestPlan.user_define_classpath")
        testplan_hash_tree = add_hash_tree(hash_tree)

        # Thread Group
        thread_group = ET.SubElement(testplan_hash_tree, "ThreadGroup",
                                     guiclass="ThreadGroupGui",
                                     testclass="ThreadGroup",
                                     testname="Thread Group",
                                     enabled="true")
        ET.SubElement(thread_group, "stringProp", name="ThreadGroup.on_sample_error").text = "continue"
        loop_ctrl = ET.SubElement(thread_group, "elementProp", name="ThreadGroup.main_controller",
                                  elementType="LoopController")
        ET.SubElement(loop_ctrl, "boolProp", name="LoopController.continue_forever").text = "false"
        ET.SubElement(loop_ctrl, "stringProp", name="LoopController.loops").text = "1"
        ET.SubElement(thread_group, "stringProp", name="ThreadGroup.num_threads").text = "1"
        ET.SubElement(thread_group, "stringProp", name="ThreadGroup.ramp_time").text = "1"
        ET.SubElement(thread_group, "boolProp", name="ThreadGroup.scheduler").text = "false"
        ET.SubElement(thread_group, "stringProp", name="ThreadGroup.duration")
        ET.SubElement(thread_group, "stringProp", name="ThreadGroup.delay")
        thread_hash_tree = add_hash_tree(testplan_hash_tree)

        # User Defined Variables
        user_vars = ET.SubElement(thread_hash_tree, "Arguments",
                                  guiclass="ArgumentsPanel",
                                  testclass="Arguments",
                                  testname="User Defined Variables",
                                  enabled="true")
        vars_coll = ET.SubElement(user_vars, "collectionProp", name="Arguments.arguments")

        # Add common variables
        for var_name in ["baseUrl", "AccessToken"]:
            var = ET.SubElement(vars_coll, "elementProp", name=var_name, elementType="Argument")
            ET.SubElement(var, "stringProp", name="Argument.name").text = var_name
            ET.SubElement(var, "stringProp", name="Argument.value").text = ""
            ET.SubElement(var, "stringProp", name="Argument.metadata").text = "="
        add_hash_tree(thread_hash_tree)

        # Process all requests
        all_requests = []
        walk_items(postman_data.get('item', []), all_requests)

        base_url_value = ""

        for req in all_requests:
            if 'request' not in req:
                continue

            request = req['request']
            raw_name = req.get("name", "Request")
            name = clean_name(raw_name)
            method = request.get("method", "GET")
            url_data = request.get("url", {})
            raw_url = url_data.get("raw", "") if isinstance(url_data, dict) else url_data

            # Extract domain and path
            domain = "${baseUrl}"
            path = "/"

            if "{{baseUrl}}" in raw_url:
                path = raw_url.replace("{{baseUrl}}", "")
            else:
                try:
                    parsed = urlparse(raw_url)
                    if not base_url_value:
                        base_url_value = f"{parsed.scheme}://{parsed.netloc}"
                    path = parsed.path
                    if parsed.query:
                        path += f"?{parsed.query}"
                except Exception:
                    pass

            # Create HTTP Sampler
            http_sampler = ET.SubElement(thread_hash_tree, "HTTPSamplerProxy",
                                         guiclass="HttpTestSampleGui",
                                         testclass="HTTPSamplerProxy",
                                         testname=name,
                                         enabled="true")
            ET.SubElement(http_sampler, "stringProp", name="HTTPSampler.domain").text = domain
            ET.SubElement(http_sampler, "stringProp", name="HTTPSampler.port")
            ET.SubElement(http_sampler, "stringProp", name="HTTPSampler.protocol").text = "https"
            ET.SubElement(http_sampler, "stringProp", name="HTTPSampler.contentEncoding")
            ET.SubElement(http_sampler, "stringProp", name="HTTPSampler.path").text = path
            ET.SubElement(http_sampler, "stringProp", name="HTTPSampler.method").text = method
            ET.SubElement(http_sampler, "boolProp", name="HTTPSampler.follow_redirects").text = "true"
            ET.SubElement(http_sampler, "boolProp", name="HTTPSampler.auto_redirects").text = "false"
            ET.SubElement(http_sampler, "boolProp", name="HTTPSampler.use_keepalive").text = "true"
            ET.SubElement(http_sampler, "boolProp", name="HTTPSampler.DO_MULTIPART_POST").text = "false"
            ET.SubElement(http_sampler, "stringProp", name="HTTPSampler.embedded_url_re").text = ""
            ET.SubElement(http_sampler, "stringProp", name="HTTPSampler.connect_timeout")
            ET.SubElement(http_sampler, "stringProp", name="HTTPSampler.response_timeout")

            # Request body handling
            args_prop = ET.SubElement(http_sampler, "elementProp", name="HTTPsampler.Arguments",
                                      elementType="Arguments")
            args_coll = ET.SubElement(args_prop, "collectionProp", name="Arguments.arguments")

            body_raw = request.get("body", {}).get("raw", "")
            if body_raw:
                ET.SubElement(http_sampler, "boolProp", name="HTTPSampler.postBodyRaw").text = "true"
                clean_body = html.unescape(body_raw)
                arg = ET.SubElement(args_coll, "elementProp", name="", elementType="HTTPArgument")
                ET.SubElement(arg, "boolProp", name="HTTPArgument.always_encode").text = "false"
                ET.SubElement(arg, "stringProp", name="Argument.name")
                sp = ET.SubElement(arg, "stringProp", name="Argument.value")
                sp.text = ET.CDATA(clean_body)
                ET.SubElement(arg, "stringProp", name="Argument.metadata").text = "="
                ET.SubElement(arg, "boolProp", name="HTTPArgument.use_equals").text = "true"
                content_type = get_content_type(request.get("header", []))
                ET.SubElement(arg, "stringProp", name="HTTPArgument.content_type").text = content_type
            else:
                ET.SubElement(http_sampler, "boolProp", name="HTTPSampler.postBodyRaw").text = "false"

            sampler_tree = add_hash_tree(thread_hash_tree)

            # Header Manager
            header_mgr = ET.SubElement(sampler_tree, "HeaderManager",
                                       guiclass="HeaderPanel",
                                       testclass="HeaderManager",
                                       testname="HTTP Header Manager",
                                       enabled="true")
            header_props = ET.SubElement(header_mgr, "collectionProp", name="HeaderManager.headers")

            # Add Authorization header if needed
            if has_auth_header(request.get("header", [])):
                token_header = ET.SubElement(header_props, "elementProp", name="", elementType="Header")
                ET.SubElement(token_header, "stringProp", name="Header.name").text = "Authorization"
                ET.SubElement(token_header, "stringProp", name="Header.value").text = "Bearer ${AccessToken}"

            # Add other headers
            for h in request.get("header", []):
                if h.get('key', '').lower() == 'authorization':
                    continue  # Skip as we handle it separately

                header = ET.SubElement(header_props, "elementProp", name="", elementType="Header")
                ET.SubElement(header, "stringProp", name="Header.name").text = h.get("key", "")
                ET.SubElement(header, "stringProp", name="Header.value").text = h.get("value", "")

            add_hash_tree(sampler_tree)

        # Set baseUrl in variables if we found one
        if base_url_value:
            for var in vars_coll:
                if var.tag == "elementProp" and var.attrib.get("name") == "baseUrl":
                    for prop in var:
                        if prop.attrib.get("name") == "Argument.value":
                            prop.text = base_url_value

        # Add listeners
        vrt = ET.SubElement(thread_hash_tree, "ResultCollector",
                            guiclass="ViewResultsFullVisualizer",
                            testclass="ResultCollector",
                            testname="View Results Tree",
                            enabled="true")
        ET.SubElement(vrt, "stringProp", name="filename")
        add_hash_tree(thread_hash_tree)

        agg = ET.SubElement(thread_hash_tree, "ResultCollector",
                            guiclass="StatGraphVisualizer",
                            testclass="ResultCollector",
                            testname="Aggregate Report",
                            enabled="true")
        ET.SubElement(agg, "stringProp", name="filename")
        add_hash_tree(thread_hash_tree)

        # Write to file
        xml = ET.tostring(root, encoding="utf-8", pretty_print=True, xml_declaration=True)
        with open(output_path, "wb") as f:
            f.write(xml)

        return output_path

    except Exception as e:
        current_app.logger.error(f"Error converting Postman to JMX: {str(e)}")
        raise


def walk_items(items, all_items):
    """Recursively walk through Postman collection items"""
    for item in items:
        if 'item' in item:
            walk_items(item['item'], all_items)
        elif 'request' in item:
            all_items.append(item)


def clean_name(name):
    """Clean request name for JMeter"""
    name = re.split(r'[\u0600-\u06FF]', name)[0].strip()  # Remove Arabic text
    name = re.sub(r'[-\s]+$', '', name.strip())
    name = re.sub(r'[^\w\s-]', '', name)  # Remove special chars
    return name or "Request"


def add_hash_tree(parent):
    """Add JMeter hashTree element"""
    return ET.SubElement(parent, "hashTree")


def extract_request_body(request):
    """Extract JSON body from Postman request"""
    body = request.get("body", {})
    if body.get("mode") == "raw":
        raw = body.get("raw", "")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def flatten_json(json_obj, prefix=''):
    """Flatten JSON structure"""
    items = {}
    if isinstance(json_obj, dict):
        for k, v in json_obj.items():
            new_key = f"{prefix}.{k}" if prefix else k
            items.update(flatten_json(v, new_key))
    elif isinstance(json_obj, list):
        for i, v in enumerate(json_obj):
            new_key = f"{prefix}[{i}]"
            items.update(flatten_json(v, new_key))
    else:
        items[prefix] = str(json_obj) if json_obj is not None else ''
    return items


def find_matching_jsonpath_by_key_and_value(json_data, target_key, target_value):
    """Find JSON path for a key-value pair"""
    match_path = None

    def search(obj, path=''):
        nonlocal match_path
        if match_path:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_path = f"{path}['{k}']" if path else f"['{k}']"
                if k == target_key and str(v) == str(target_value):
                    match_path = new_path
                    return
                search(v, new_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                new_path = f"{path}[{i}]"
                search(item, new_path)

    search(json_data)
    return match_path


def get_request_url(request):
    """Get URL from Postman request"""
    url_data = request.get("url", {})
    if isinstance(url_data, dict):
        return url_data.get("raw", "")
    return url_data


def get_content_type(headers):
    """Get content type from headers"""
    for h in headers:
        if h.get('key', '').lower() == 'content-type':
            return h.get('value', 'application/json')
    return 'application/json'


def has_auth_header(headers):
    """Check if request has authorization header"""
    for h in headers:
        if h.get('key', '').lower() == 'authorization':
            return True
    return False


def generate_jmx_with_gpt(postman_json, correlation_data):
    """Generate JMX using GPT-4"""
    try:
        full_prompt = (
            "You are a senior QA automation engineer. Convert the following Postman collection into a JMeter JMX test plan. "
            "Apply dynamic value correlations using JSON Extractors wherever applicable, based on the correlation mapping below.\n\n"
            "=== Postman Collection JSON ===\n"
            f"{json.dumps(postman_json, indent=2)}\n\n"
            "=== Correlation Mapping ===\n"
            f"{json.dumps(correlation_data, indent=2)}\n\n"
            "Please return the JMeter JMX XML content as output only. Make sure the structure is valid and ready to import in JMeter."
        )

        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a senior QA automation engineer."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.3
        )

        result = completion['choices'][0]['message']['content']
        output_path = os.path.join(
            current_app.config['UPLOAD_FOLDER'],
            f"generated_test_plan_{uuid.uuid4().hex[:8]}.jmx"
        )

        with open(output_path, "w", encoding='utf-8') as f:
            f.write(result)

        return output_path

    except Exception as e:
        current_app.logger.error(f"Error generating JMX with GPT: {str(e)}")
        raise