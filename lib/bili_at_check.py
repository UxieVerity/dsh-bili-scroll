#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bili_at_check.py —— 给「@ 即时回复」用的检查器（宿主每分钟调它一次）。

职责只有三件：
  1. 读 B站 最近收到的 @ 通知
  2. 只保留设置里 mentionUid 那个号发来的（没填 UID 就一条都不给）
  3. 跟 mentions-done.json 比对，只吐出「还没处理过」的那几条（JSON 打到 stdout）

⚠️ 它**只读不写评论**：回复由模型那一小回合去做，免得这里又长出一只手。
"""
import json
import os
import sys

_HOME = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HOME)

DONE_FILE = os.path.join(_HOME, 'mentions-done.json')
CFG_FILE = os.path.join(_HOME, 'config.json')


def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    cfg = load_json(CFG_FILE, {})
    uid = int(cfg.get('mentionUid') or 0)
    if uid <= 0:
        print(json.dumps({'ok': True, 'new': [], 'reason': 'no_mention_uid'}, ensure_ascii=False))
        return 0

    try:
        import asyncio
        import mcp_server as m
    except Exception as e:
        print(json.dumps({'ok': False, 'error': 'import: %s: %s' % (type(e).__name__, e)}, ensure_ascii=False))
        return 0

    async def fetch():
        cred = m.get_cred()
        return await m.session.get_at(credential=cred)

    try:
        at = asyncio.run(fetch())
    except Exception as e:
        print(json.dumps({'ok': False, 'error': 'fetch: %s: %s' % (type(e).__name__, e)}, ensure_ascii=False))
        return 0

    done = set(str(x) for x in load_json(DONE_FILE, {}).get('done', []))
    items = (at or {}).get('items', []) or []
    new = []
    for it in items:
        user = it.get('user') or {}
        if int(user.get('mid') or 0) != uid:
            continue
        d = it.get('item') or {}
        cid = str(d.get('source_id') or it.get('id') or '')
        if not cid or cid in done:
            continue
        uri = str(d.get('uri') or '')
        bvid = ''
        if '/video/' in uri:
            bvid = uri.split('/video/')[-1].split('?')[0].strip()
        new.append({
            'comment_id': cid,
            'bvid': bvid,
            'nickname': user.get('nickname') or '',
            'text': (d.get('source_content') or '').strip(),
            'video_title': d.get('title') or '',
            'uri': uri,
        })

    print(json.dumps({'ok': True, 'new': new, 'total_at': len(items)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
