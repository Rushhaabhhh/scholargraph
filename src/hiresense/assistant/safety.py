"""Defense in depth. Tool authority comes from typed server routing, never data."""

import re
import unicodedata

_PATTERNS = tuple(re.compile(pattern, re.I) for pattern in (
    r'ignore\s+(?:(?:all|any|the|previous|prior|above)\s+){0,3}(?:instructions|rules|messages)',
    r'\b(?:reveal|print|exfiltrate|steal)\b.{0,50}\b(?:secret|key|prompt|memory)\b',
    r'(?:^|[\n])\s*(?:system|developer)\s*:',
    r'\[\s*(?:system|developer|assistant|tool)\s*\]',
    r'<\|(?:im_start|im_end|system|assistant|tool)',
    r'</?\s*(?:system|assistant|tool)\s*>',
    r'\b(?:call|invoke|execute)\s+(?:the\s+)?(?:tool|function)\b',
    r'\b(?:drop\s+table|delete\s+from|forget\s+all\s+rules)\b',
))


def normalized_text(text):
    return ''.join(char for char in unicodedata.normalize('NFKC', text)
                   if unicodedata.category(char) != 'Cf')


def injection_like(text):
    text = normalized_text(text)
    return any(pattern.search(text) for pattern in _PATTERNS)


def data_warnings(text):
    return ['instruction_like_source_text'] if injection_like(text) else []
