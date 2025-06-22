import json
from lxml import etree as ET
from .correlation_utils import clean_and_parse_xml

def debug_jmeter_xml(xml_path):
    """Generate a detailed debug report of all HTTP samples in the XML file"""
    all_samples = []
    total_count = 0
    
    try:
        root = clean_and_parse_xml(xml_path)
    except Exception as e:
        return {"error": f"Failed to parse XML: {str(e)}"}
    
    def collect_all_samples(node):
        nonlocal total_count
        
        # Check if this is a sample node
        is_sample = False
        if node.tag is not None:
            tag_name = node.tag.split('}')[-1] if '}' in node.tag else node.tag
            is_sample = tag_name.endswith('Sample') or tag_name == 'sample'
        
        if is_sample:
            total_count += 1
            sample_info = {
                "index": total_count,
                "tag": node.tag,
                "label": node.get('lb', 'No_Label'),
                "method": node.findtext('method', 'UNKNOWN'),
                "available_elements": []
            }
            
            # Collect all available elements
            for elem in node:
                if elem.tag and elem.text:
                    tag = elem.tag.split('}')[-1]
                    text_preview = (elem.text[:50] + '...') if elem.text and len(elem.text) > 50 else elem.text
                    sample_info["available_elements"].append({
                        "tag": tag,
                        "text_preview": text_preview
                    })
            
            # Try to get URL from various locations
            url = None
            for url_path in ['java.net.URL', 'URL', 'url']:
                url_text = node.findtext(url_path)
                if url_text:
                    url = url_text
                    break
            
            sample_info["url"] = url
            all_samples.append(sample_info)
        
        # Process child nodes
        for child in node:
            collect_all_samples(child)
    
    collect_all_samples(root)
    
    return {
        "total_samples": total_count,
        "samples": all_samples
    }
