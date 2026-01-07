# directory/utils/docx_vml.py
"""
Utilities for replacing text inside VML WordArt shapes in DOCX files.
"""
import io
import logging
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, Any, Iterable

logger = logging.getLogger(__name__)

VML_NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'v': 'urn:schemas-microsoft-com:vml',
}


def _replace_vml_text(xml_bytes: bytes, replacements: Dict[str, str]) -> bytes:
    root = ET.fromstring(xml_bytes)
    updated = False

    for vshape in root.findall('.//v:shape', VML_NS):
        name = vshape.attrib.get('id') or vshape.attrib.get('alt')
        if not name or name not in replacements:
            continue

        new_text = replacements.get(name, '')
        text_nodes = vshape.findall('.//w:t', VML_NS)
        if not text_nodes:
            logger.debug("No text nodes found for VML shape '%s'", name)
            continue

        # Put new text into the first node and clear the rest.
        text_nodes[0].text = new_text
        for node in text_nodes[1:]:
            node.text = ''

        updated = True

    if not updated:
        return xml_bytes
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def replace_vml_text_in_docx(docx_bytes: bytes, replacements: Dict[str, Any]) -> bytes:
    """
    Replace VML WordArt text by shape name in a DOCX file.

    Args:
        docx_bytes: DOCX content as bytes.
        replacements: Mapping from VML shape name (id/alt) to replacement text.
    """
    if not replacements:
        return docx_bytes

    normalized = {str(k): '' if v is None else str(v) for k, v in replacements.items()}
    targets = ('word/document.xml',)

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx_bytes), 'r') as zin:
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename in targets or item.filename.startswith('word/header') or item.filename.startswith('word/footer'):
                    try:
                        data = _replace_vml_text(data, normalized)
                    except Exception as exc:
                        logger.warning("VML replace failed for %s: %s", item.filename, exc)
                zout.writestr(item, data)

    return output.getvalue()
