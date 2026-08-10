#!/usr/bin/env python3
"""Decode Google's deferred-HTML (window.jsl.dh) payloads into one flat HTML doc."""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))

_ESC = re.compile(r'\\(?:x([0-9a-fA-F]{2})|u([0-9a-fA-F]{4})|(.))')


def _un(m):
    if m.group(1):
        return chr(int(m.group(1), 16))
    if m.group(2):
        return chr(int(m.group(2), 16))
    c = m.group(3)
    return {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '"': '"', "'": "'",
            '/': '/', 'b': '\b', 'f': '\f', '0': '\0'}.get(c, c)


def js_unescape(s):
    return _ESC.sub(_un, s)


def decoded_html(path):
    raw = open(path, encoding='utf-8').read()
    parts = [raw]
    # window.jsl.dh("id","<html>")  -- second arg is a JS string literal
    for m in re.finditer(r'window\.jsl\.dh\("[^"]*","', raw):
        i = m.end()
        buf = []
        while i < len(raw):
            ch = raw[i]
            if ch == '\\':
                buf.append(raw[i:i + 2]); i += 2; continue
            if ch == '"':
                break
            buf.append(ch); i += 1
        parts.append(js_unescape(''.join(buf)))
    return '\n'.join(parts)


if __name__ == '__main__':
    for f in sorted(os.listdir(HERE)):
        if f.endswith('.html') and not f.endswith('.decoded.html'):
            d = decoded_html(os.path.join(HERE, f))
            out = os.path.join(HERE, 'decoded', f)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, 'w', encoding='utf-8').write(d)
            print(f, len(d))
