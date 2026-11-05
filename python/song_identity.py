"""Shared identity normalization; no song/artist is inferred from a title alone."""
import html
import re
import unicodedata
from opencc import OpenCC

_chinese = OpenCC('t2s')

def plain(text):
    return _chinese.convert(unicodedata.normalize('NFKC', html.unescape(re.sub('<[^>]+>', '', str(text))))).strip()

def name_key(text):
    return re.sub(r'[\W_]+', '', plain(text)).casefold()

def canonical_artist(text):
    clean = plain(text)
    compact = re.sub(r'\s+', '', clean).casefold()
    if compact in {'周杰伦', 'jaychou', '周杰伦jaychou', 'jaychou周杰伦'}:
        return '周杰伦'
    return clean

def artist_key(text):
    # Keep punctuation: a fake artist called 周深- is not the actual 周深.
    return re.sub(r'\s+', '', canonical_artist(text)).casefold()

def prefer_bilibili(artist):
    return canonical_artist(artist) == '周杰伦'
