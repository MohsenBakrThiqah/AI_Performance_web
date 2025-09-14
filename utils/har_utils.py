import os
import json
import urllib.parse
import base64
import re
import traceback
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom

# This file contains refactored helper functions from the original Tkinter HAR tool
# so they can be reused in the Flask web application.

__all__ = [
    'extract_base_urls', 'extract_methods', 'extract_path_extensions',
    'har_to_jmeter_xml', 'har_to_jmeter_jmx'
]


def sanitize_for_xml(text):
    if text is None:
        return ''
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    text = text.replace('&', '&amp;').replace('<', '&lt;')
    text = text.replace("'", '&apos;')
    return text


def fix_malformed_json(json_data: str) -> str:
    for char in range(0, 32):
        if char not in (9, 10, 13):
            json_data = json_data.replace(chr(char), '')
    json_data = re.sub(r'([{,])\s*([a-zA-Z0-9_]+)\s*:', r'"\1"', json_data)
    json_data = re.sub(r',\s*([}\]])', r'\1', json_data)
    json_data = re.sub(r'([}\]"])\s*([{["a-zA-Z0-9])', r'\1,\2', json_data)
    return json_data


def _load_har(har_file):
    with open(har_file, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        fixed = fix_malformed_json(content)
        return json.loads(fixed)


def extract_base_urls(har_file):
    try:
        har_data = _load_har(har_file)
        log_data = har_data.get('log', {}) if isinstance(har_data, dict) else {}
        entries = log_data.get('entries', []) if isinstance(log_data, dict) else []
        base_urls = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            req = entry.get('request', {}) if isinstance(entry.get('request'), dict) else {}
            url = req.get('url', '') or ''
            if not url:
                continue
            try:
                parsed = urllib.parse.urlparse(url)
                base_urls.add(f"{parsed.scheme}://{parsed.netloc}")
            except Exception:
                continue
        return sorted(base_urls)
    except Exception:
        return []


def extract_methods(har_file):
    try:
        har_data = _load_har(har_file)
        log_data = har_data.get('log', {}) if isinstance(har_data, dict) else {}
        entries = log_data.get('entries', []) if isinstance(log_data, dict) else []
        methods = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            req = entry.get('request', {}) if isinstance(entry.get('request'), dict) else {}
            method = (req.get('method') or '').upper()
            if method:
                methods.add(method)
        std = ['GET','POST','PUT','DELETE','HEAD','OPTIONS','PATCH','TRACE']
        ordered = [m for m in std if m in methods]
        for m in ordered:
            methods.discard(m)
        return ordered + sorted(methods)
    except Exception:
        return []


def extract_path_extensions(har_file):
    try:
        har_data = _load_har(har_file)
        log_data = har_data.get('log', {}) if isinstance(har_data, dict) else {}
        entries = log_data.get('entries', []) if isinstance(log_data, dict) else []
        exts = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            req = entry.get('request', {}) if isinstance(entry.get('request'), dict) else {}
            url = req.get('url', '') or ''
            if not url:
                continue
            try:
                parsed = urllib.parse.urlparse(url)
                path = parsed.path or ''
                if path.endswith('/'):
                    continue
                _, ext = os.path.splitext(path)
                if ext and re.fullmatch(r'\.[A-Za-z0-9]{1,8}', ext):
                    exts.add(ext.lower())
            except Exception:
                continue
        return sorted(exts)
    except Exception:
        return []


def _should_include_by_extension(path, selected_extensions):
    """Decide inclusion based on extension selection rules.
    selected_extensions None -> no extension filtering
    selected_extensions [] (empty list) -> user unchecked all: exclude any request having a file extension
    selected_extensions [..values..] -> include only if extension in list (case-insensitive)
    Paths without an extension are always included unless explicitly filtered otherwise.
    """
    if selected_extensions is None:
        return True  # no filtering
    parsed_ext = os.path.splitext(path)[1].lower()
    if not parsed_ext:
        return True  # no extension => treat as acceptable
    if len(selected_extensions) == 0:
        # User unchecked all: exclude paths that DO have an extension
        return False
    # Non-empty list: allow only if extension in selected list
    return parsed_ext in selected_extensions


def create_sample_result(entry, index):
    # Simplified version (nearly identical logic) used for recording.xml
    try:
        request = entry.get('request', {}) if isinstance(entry.get('request'), dict) else {}
        response = entry.get('response', {}) if isinstance(entry.get('response'), dict) else {}
        url = str(request.get('url', '') or '')
        method = (request.get('method') or 'GET').upper()
        if method not in ['GET','POST','PUT','DELETE','HEAD','OPTIONS','PATCH','TRACE']:
            method = 'GET'
        try:
            parsed_url = urllib.parse.urlparse(url)
            path = parsed_url.path if parsed_url.path else '/'
        except Exception:
            path = '/'
        start_time = entry.get('startedDateTime', '')
        try:
            timestamp = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp() * 1000
        except Exception:
            try:
                timestamp = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ").timestamp() * 1000
            except Exception:
                timestamp = 0
        sample = ET.Element('httpSample')
        time_taken = float(entry.get('time', 0))
        sample.set('t', str(int(time_taken)))
        sample.set('lt', str(int(time_taken)))
        sample.set('ct', '0')
        sample.set('it', '0')
        sample.set('ts', str(int(timestamp)))
        status_code = int(response.get('status', 0) or 0)
        sample.set('s', 'true' if 100 <= status_code < 400 else 'false')
        sample.set('lb', f"{index:03d}_{method}_{path}")
        sample.set('rc', str(status_code))
        sample.set('rm', str(response.get('statusText', '') or ''))
        sample.set('tn', 'Thread Group 1-1')
        sample.set('dt', 'text')
        sample.set('by', str(response.get('bodySize', 0) or 0))
        sample.set('na', '1')
        sample.set('ng', '1')
        sample.set('method', method)
        # Headers
        headers_txt = ''
        for h in request.get('headers', []) or []:
            if isinstance(h, dict):
                name = sanitize_for_xml(h.get('name',''))
                value = sanitize_for_xml(h.get('value',''))
                headers_txt += f"{name}: {value}\n"
        ET.SubElement(sample, 'requestHeader', {'class':'java.lang.String'}).text = headers_txt
        ET.SubElement(sample, 'method', {'class':'java.lang.String'}).text = method
        # Response headers
        resp_headers_txt = ''
        for h in response.get('headers', []) or []:
            if isinstance(h, dict):
                name = sanitize_for_xml(h.get('name',''))
                value = sanitize_for_xml(h.get('value',''))
                resp_headers_txt += f"{name}: {value}\n"
        ET.SubElement(sample, 'responseHeader', {'class':'java.lang.String'}).text = resp_headers_txt
        # Response body
        content = response.get('content', {}) if isinstance(response.get('content'), dict) else {}
        body = content.get('text','') or ''
        if (content.get('encoding','') or '').lower() == 'base64':
            try:
                body = base64.b64decode(body).decode('utf-8', errors='replace')
            except Exception:
                body = '[Binary data]'
        ET.SubElement(sample, 'responseData', {'class':'java.lang.String'}).text = sanitize_for_xml(body)
        ET.SubElement(sample, 'java.net.URL').text = sanitize_for_xml(url)
        return sample
    except Exception as e:
        sample = ET.Element('httpSample')
        sample.set('lb', f'Error {index}: {e}')
        return sample


def har_to_jmeter_xml(har_file, output_file, selected_urls=None, selected_methods=None, selected_extensions=None, status_callback=None):
    try:
        # Normalize extension selections (lowercase + strip) to ensure reliable comparison
        if selected_extensions is not None:
            selected_extensions = [e.lower().strip() for e in selected_extensions if e]
        har_data = _load_har(har_file)
        log_data = har_data.get('log', {}) if isinstance(har_data, dict) else {}
        entries = log_data.get('entries', []) if isinstance(log_data, dict) else []
        if selected_urls or selected_methods or selected_extensions is not None:
            filtered = []
            for entry in entries:
                try:
                    req = entry.get('request', {}) if isinstance(entry.get('request'), dict) else {}
                    url = req.get('url','') or ''
                    method = (req.get('method') or '').upper()
                    include = True
                    if selected_urls and url:
                        pu = urllib.parse.urlparse(url)
                        base_url = f"{pu.scheme}://{pu.netloc}"
                        if base_url not in selected_urls:
                            include = False
                    if include and selected_methods and method and method not in selected_methods:
                        include = False
                    if include and selected_extensions is not None:
                        pu = urllib.parse.urlparse(url)
                        path = pu.path or ''
                        if not _should_include_by_extension(path, selected_extensions):
                            include = False
                    if include:
                        filtered.append(entry)
                except Exception:
                    continue
            entries = filtered
        root = ET.Element('testResults')
        root.set('version','1.2')
        for idx, entry in enumerate(entries, start=1):
            root.append(create_sample_result(entry, idx))
        try:
            xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(indent='  ')
        except Exception:
            xmlstr = ET.tostring(root, encoding='unicode')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(xmlstr)
        return True, f'Successfully converted HAR to recording.xml with {len(entries)} samples.'
    except Exception as e:
        return False, f'Error: {e}\n{traceback.format_exc()}'


def har_to_jmeter_jmx(har_file, output_file, selected_urls=None, selected_methods=None, selected_extensions=None, status_callback=None, use_transaction_controllers=False):
    # Builds a minimal but valid JMeter Test Plan structure.
    def is_json_body(txt):
        if not txt:
            return False
        t = txt.strip()
        if not ((t.startswith('{') and t.endswith('}')) or (t.startswith('[') and t.endswith(']'))):
            return False
        try:
            json.loads(t)
            return True
        except Exception:
            return False
    try:
        # Normalize extension selections (lowercase + strip) to ensure reliable comparison
        if selected_extensions is not None:
            selected_extensions = [e.lower().strip() for e in selected_extensions if e]
        har_data = _load_har(har_file)
        log_data = har_data.get('log', {}) if isinstance(har_data, dict) else {}
        entries = log_data.get('entries', []) if isinstance(log_data, dict) else []
        # Filtering logic (reuse from XML path)
        if selected_urls or selected_methods or selected_extensions is not None:
            filtered = []
            for entry in entries:
                try:
                    req = entry.get('request', {}) if isinstance(entry.get('request'), dict) else {}
                    url = req.get('url','') or ''
                    method = (req.get('method') or '').upper()
                    include = True
                    if selected_urls and url:
                        pu = urllib.parse.urlparse(url)
                        base_url = f"{pu.scheme}://{pu.netloc}"
                        if base_url not in selected_urls:
                            include = False
                    if include and selected_methods and method and method not in selected_methods:
                        include = False
                    if include and selected_extensions is not None:
                        pu = urllib.parse.urlparse(url)
                        path = pu.path or ''
                        if not _should_include_by_extension(path, selected_extensions):
                            include = False
                    if include:
                        filtered.append(entry)
                except Exception:
                    continue
            entries = filtered

        # Root Test Plan structure
        test_plan = ET.Element('jmeterTestPlan', version='1.2', properties='5.0', jmeter='5.5')
        root_ht = ET.SubElement(test_plan, 'hashTree')

        # TestPlan element + hashTree
        tp = ET.SubElement(root_ht, 'TestPlan', guiclass='TestPlanGui', testclass='TestPlan', testname='HAR Imported Test Plan', enabled='true')
        ET.SubElement(tp, 'stringProp', name='TestPlan.comments').text = ''
        ET.SubElement(tp, 'boolProp', name='TestPlan.functional_mode').text = 'false'
        ET.SubElement(tp, 'boolProp', name='TestPlan.serialize_threadgroups').text = 'false'
        user_vars = ET.SubElement(tp, 'elementProp', name='TestPlan.user_defined_variables', elementType='Arguments', guiclass='ArgumentsPanel', testclass='Arguments', testname='User Defined Variables', enabled='true')
        ET.SubElement(user_vars, 'collectionProp', name='Arguments.arguments')
        ET.SubElement(tp, 'stringProp', name='TestPlan.user_define_classpath').text = ''
        tp_ht = ET.SubElement(root_ht, 'hashTree')

        # --- Required default config elements (in order) ---
        # 1. User Defined Variables (Arguments) element
        args_top = ET.SubElement(tp_ht, 'Arguments', guiclass='ArgumentsPanel', testclass='Arguments', testname='User Defined Variables', enabled='true')
        ET.SubElement(args_top, 'collectionProp', name='Arguments.arguments')
        ET.SubElement(tp_ht, 'hashTree')
        # 2. HTTP Request Defaults
        http_defaults = ET.SubElement(tp_ht, 'ConfigTestElement', guiclass='HttpDefaultsGui', testclass='ConfigTestElement', testname='HTTP Request Defaults', enabled='true')
        ET.SubElement(http_defaults, 'boolProp', name='HTTPSampler.concurrentDwn').text = 'true'
        ET.SubElement(http_defaults, 'intProp', name='HTTPSampler.concurrentPool').text = '6'
        http_def_args = ET.SubElement(http_defaults, 'elementProp', name='HTTPsampler.Arguments', elementType='Arguments', guiclass='HTTPArgumentsPanel', testclass='Arguments', testname='User Defined Variables')
        ET.SubElement(http_def_args, 'collectionProp', name='Arguments.arguments')
        ET.SubElement(http_defaults, 'stringProp', name='HTTPSampler.implementation')
        ET.SubElement(tp_ht, 'hashTree')
        # 3. DNS Cache Manager
        dns_mgr = ET.SubElement(tp_ht, 'DNSCacheManager', guiclass='DNSCachePanel', testclass='DNSCacheManager', testname='DNS Cache Manager', enabled='true')
        ET.SubElement(dns_mgr, 'collectionProp', name='DNSCacheManager.servers')
        ET.SubElement(dns_mgr, 'collectionProp', name='DNSCacheManager.hosts')
        ET.SubElement(dns_mgr, 'boolProp', name='DNSCacheManager.clearEachIteration').text = 'true'
        ET.SubElement(dns_mgr, 'boolProp', name='DNSCacheManager.isCustomResolver').text = 'false'
        ET.SubElement(tp_ht, 'hashTree')
        # 4. Cookie Manager
        cookie_mgr = ET.SubElement(tp_ht, 'CookieManager', guiclass='CookiePanel', testclass='CookieManager', testname='HTTP Cookie Manager', enabled='true')
        ET.SubElement(cookie_mgr, 'collectionProp', name='CookieManager.cookies')
        ET.SubElement(cookie_mgr, 'boolProp', name='CookieManager.clearEachIteration').text = 'true'
        ET.SubElement(cookie_mgr, 'boolProp', name='CookieManager.controlledByThreadGroup').text = 'false'
        ET.SubElement(tp_ht, 'hashTree')
        # 5. Cache Manager
        cache_mgr = ET.SubElement(tp_ht, 'CacheManager', guiclass='CacheManagerGui', testclass='CacheManager', testname='HTTP Cache Manager', enabled='true')
        ET.SubElement(cache_mgr, 'boolProp', name='clearEachIteration').text = 'true'
        ET.SubElement(cache_mgr, 'boolProp', name='useExpires').text = 'false'
        ET.SubElement(cache_mgr, 'boolProp', name='CacheManager.controlledByThread').text = 'false'
        ET.SubElement(tp_ht, 'hashTree')
        # --- End default config elements ---

        # Thread Group + hashTree
        tg = ET.SubElement(tp_ht, 'ThreadGroup', guiclass='ThreadGroupGui', testclass='ThreadGroup', testname='Thread Group', enabled='true')
        ET.SubElement(tg, 'stringProp', name='ThreadGroup.on_sample_error').text = 'continue'
        loop_ctrl = ET.SubElement(tg, 'elementProp', name='ThreadGroup.main_controller', elementType='LoopController', guiclass='LoopControlPanel', testclass='LoopController', testname='Loop Controller', enabled='true')
        ET.SubElement(loop_ctrl, 'boolProp', name='LoopController.continue_forever').text = 'false'
        ET.SubElement(loop_ctrl, 'stringProp', name='LoopController.loops').text = '1'
        ET.SubElement(tg, 'stringProp', name='ThreadGroup.num_threads').text = '1'
        ET.SubElement(tg, 'stringProp', name='ThreadGroup.ramp_time').text = '1'
        ET.SubElement(tg, 'longProp', name='ThreadGroup.start_time').text = '0'
        ET.SubElement(tg, 'longProp', name='ThreadGroup.end_time').text = '0'
        ET.SubElement(tg, 'boolProp', name='ThreadGroup.scheduler').text = 'false'
        ET.SubElement(tg, 'stringProp', name='ThreadGroup.duration').text = ''
        ET.SubElement(tg, 'stringProp', name='ThreadGroup.delay').text = ''
        tg_ht = ET.SubElement(tp_ht, 'hashTree')

        def minute_key(entry):
            start = entry.get('startedDateTime','')
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ","%Y-%m-%dT%H:%M:%S.%f%z","%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%SZ","%Y-%m-%dT%H:%M:%S"):
                try:
                    s = start.replace('Z','+00:00') if fmt.endswith('%z') else start
                    dt = datetime.strptime(s, fmt)
                    return dt.strftime('%Y-%m-%d %H:%M')
                except Exception:
                    continue
            try:
                dt = datetime.fromisoformat(start.replace('Z','+00:00'))
                return dt.strftime('%Y-%m-%d %H:%M')
            except Exception:
                return 'Unknown'

        def add_sampler(entry, idx, parent_ht):
            try:
                req = entry.get('request', {}) if isinstance(entry.get('request'), dict) else {}
                url = req.get('url','') or ''
                method = (req.get('method') or 'GET').upper()
                if method not in ['GET','POST','PUT','DELETE','HEAD','OPTIONS','PATCH','TRACE']:
                    method = 'GET'
                parsed = urllib.parse.urlparse(url)
                path_only = parsed.path or '/'
                query_string = parsed.query or ''
                # Label keeps original (with query if present) for easier traceability
                label_full_path = path_only + (('?' + query_string) if query_string else '')
                label = f"{idx:03d}_{method}_{label_full_path}"[:200]
                sampler = ET.SubElement(parent_ht, 'HTTPSamplerProxy', guiclass='HttpTestSampleGui', testclass='HTTPSamplerProxy', testname=label, enabled='true')
                post_body_raw = False  # will set true if we add a raw body argument
                args = ET.SubElement(sampler, 'elementProp', name='HTTPsampler.Arguments', elementType='Arguments')
                args_coll = ET.SubElement(args, 'collectionProp', name='Arguments.arguments')
                ET.SubElement(sampler, 'stringProp', name='HTTPSampler.domain').text = parsed.hostname or ''
                ET.SubElement(sampler, 'stringProp', name='HTTPSampler.port').text = str(parsed.port or '')
                ET.SubElement(sampler, 'stringProp', name='HTTPSampler.protocol').text = parsed.scheme or ''
                # (Defer adding path until after body & query logic)
                ET.SubElement(sampler, 'stringProp', name='HTTPSampler.method').text = method
                ET.SubElement(sampler, 'boolProp', name='HTTPSampler.follow_redirects').text = 'true'
                ET.SubElement(sampler, 'boolProp', name='HTTPSampler.auto_redirects').text = 'false'
                ET.SubElement(sampler, 'boolProp', name='HTTPSampler.use_keepalive').text = 'true'
                ET.SubElement(sampler, 'boolProp', name='HTTPSampler.DO_MULTIPART_POST').text = 'false'
                ET.SubElement(sampler, 'stringProp', name='HTTPSampler.embedded_url_re').text = ''
                ET.SubElement(sampler, 'stringProp', name='HTTPSampler.connect_timeout').text = ''
                ET.SubElement(sampler, 'stringProp', name='HTTPSampler.response_timeout').text = ''
                # Body (raw) handling
                post_data = ''
                if method in ('POST','PUT','PATCH','DELETE'):
                    post_obj = req.get('postData') if isinstance(req.get('postData'), dict) else None
                    if post_obj:
                        txt = post_obj.get('text','') or ''
                        if txt:
                            post_data = txt
                    if post_data:
                        post_body_raw = True
                        body_arg = ET.SubElement(args_coll, 'elementProp', name='', elementType='HTTPArgument')
                        ET.SubElement(body_arg, 'boolProp', name='HTTPArgument.always_encode').text = 'false'
                        ET.SubElement(body_arg, 'stringProp', name='Argument.value').text = sanitize_for_xml(post_data)
                        ET.SubElement(body_arg, 'stringProp', name='Argument.metadata').text = '='
                        ET.SubElement(body_arg, 'boolProp', name='HTTPArgument.use_equals').text = 'true'
                # Query parameters: only convert to arguments if (a) query exists AND (b) we are NOT using a raw body
                if query_string and not post_body_raw:
                    for q_name, q_value in urllib.parse.parse_qsl(query_string, keep_blank_values=True):
                        q_arg = ET.SubElement(args_coll, 'elementProp', name=q_name, elementType='HTTPArgument')
                        ET.SubElement(q_arg, 'boolProp', name='HTTPArgument.always_encode').text = 'false'
                        ET.SubElement(q_arg, 'stringProp', name='Argument.name').text = sanitize_for_xml(q_name)
                        ET.SubElement(q_arg, 'stringProp', name='Argument.value').text = sanitize_for_xml(q_value)
                        ET.SubElement(q_arg, 'stringProp', name='Argument.metadata').text = '='
                        ET.SubElement(q_arg, 'boolProp', name='HTTPArgument.use_equals').text = 'true'
                    final_path = path_only  # path without query
                else:
                    final_path = label_full_path if query_string else path_only
                # Now add the path element (avoid double escaping of '&' when keeping query in path)
                path_text = sanitize_for_xml(final_path)
                if post_body_raw and query_string:
                    # We intentionally kept the query string inside the path (because a raw body exists).
                    # sanitize_for_xml already turned '&' into '&amp;'. If we leave it that way, the XML
                    # serializer will treat '&amp;' as literal entity text and JMeter may display '&amp;' in GUI.
                    # Converting back to '&' here lets the serializer escape it exactly once, yielding '&' in GUI.
                    path_text = path_text.replace('&amp;', '&')
                ET.SubElement(sampler, 'stringProp', name='HTTPSampler.path').text = path_text
                ET.SubElement(sampler, 'boolProp', name='HTTPSampler.postBodyRaw').text = 'true' if post_body_raw else 'false'
                # Sampler hashTree
                sampler_ht = ET.SubElement(parent_ht, 'hashTree')
                # Header Manager
                headers = req.get('headers') if isinstance(req.get('headers'), list) else []
                if headers:
                    hm = ET.SubElement(sampler_ht, 'HeaderManager', guiclass='HeaderPanel', testclass='HeaderManager', testname='HTTP Header Manager', enabled='true')
                    hm_coll = ET.SubElement(hm, 'collectionProp', name='HeaderManager.headers')
                    for h in headers:
                        if not isinstance(h, dict):
                            continue
                        name = h.get('name') or ''
                        value = h.get('value') or ''
                        if not name:
                            continue
                        h_el = ET.SubElement(hm_coll, 'elementProp', name=name, elementType='Header')
                        ET.SubElement(h_el, 'stringProp', name='Header.name').text = sanitize_for_xml(name)
                        ET.SubElement(h_el, 'stringProp', name='Header.value').text = sanitize_for_xml(value)
                    ET.SubElement(sampler_ht, 'hashTree')
                return True
            except Exception:
                return False

        if use_transaction_controllers:
            groups = {}
            for i, entry in enumerate(entries, start=1):
                groups.setdefault(minute_key(entry), []).append((i, entry))
            for minute in sorted(groups.keys()):
                tc = ET.SubElement(tg_ht, 'TransactionController', guiclass='TransactionControllerGui', testclass='TransactionController', testname=minute, enabled='true')
                ET.SubElement(tc, 'boolProp', name='TransactionController.includeTimers').text = 'false'
                ET.SubElement(tc, 'boolProp', name='TransactionController.generateParentSample').text = 'false'
                tc_ht = ET.SubElement(tg_ht, 'hashTree')
                for i, entry in groups[minute]:
                    add_sampler(entry, i, tc_ht)
        else:
            for i, entry in enumerate(entries, start=1):
                add_sampler(entry, i, tg_ht)

        # Pretty print
        try:
            xmlstr = minidom.parseString(ET.tostring(test_plan)).toprettyxml(indent='  ')
        except Exception:
            xmlstr = ET.tostring(test_plan, encoding='unicode')
        # --- Post-process: wrap any HTTPSampler.path containing a query string in CDATA so '&' renders properly in JMeter UI ---
        try:
            def _path_cdata_repl(m):
                raw = m.group(1)
                # Unescape any existing &amp; back to & for readability inside CDATA
                raw_unescaped = raw.replace('&amp;', '&')
                return f'<stringProp name="HTTPSampler.path"><![CDATA[{raw_unescaped}]]></stringProp>'
            import re as _re
            xmlstr = _re.sub(r'<stringProp name="HTTPSampler.path">([^<]*\?[^<]*)</stringProp>', _path_cdata_repl, xmlstr)
        except Exception:
            pass
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(xmlstr)
        return True, f'Successfully created JMX with {len(entries)} samplers.'
    except Exception as e:
        return False, f'Error: {e}\n{traceback.format_exc()}'
