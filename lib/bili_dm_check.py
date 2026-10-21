#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bili_dm_check.py —— 给「私信即时回复」用的检查器（宿主每分钟跳一次，实际 2 分钟一轮）。

职责三件：
  1. 只读 config.json 里 dmReplyUids 名单中那些 UID 的会话（**别人发的私信一概不读**）
  2. 只挑「对方发来的、还没处理过的」消息（对比 dm-done.json）
  3. 把新消息以 JSON 吐到 stdout，交给模型那一小回合去回

⚠️ 只读不写：发消息由模型回合调 bili_send_message 完成（那边还有一道白名单闸）。
⚠️ 任何异常都吞掉并输出 ok:false —— 绝不能让宿主崩。
"""
import json
import os
import sys

_HOME = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HOME)

DONE_FILE = os.path.join(_HOME, 'dm-done.json')
CFG_FILE = os.path.join(_HOME, 'config.json')


def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def text_of(msg):
    """私信正文可能是纯字符串，也可能是 JSON 串 {"content": "..."}"""
    raw = msg.get('content')
    if isinstance(raw, dict):
        return str(raw.get('content') or '').strip()
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith('{'):
            try:
                return str(json.loads(s).get('content') or '').strip()
            except Exception:
                return s
        return s
    return ''


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    cfg = load_json(CFG_FILE, {})
    raw_uids = cfg.get('dmReplyUids') or []
    uids = []
    for x in raw_uids:
        try:
            n = int(str(x).strip())
            if n > 0 and n not in uids:
                uids.append(n)
        except Exception:
            continue
    if not uids:
        print(json.dumps({'ok': True, 'new': [], 'reason': 'no_dm_reply_uids'}, ensure_ascii=False))
        return 0

    try:
        import asyncio
        import mcp_server as m
        from bilibili_api import session as S
    except Exception as e:
        print(json.dumps({'ok': False, 'error': 'import: %s: %s' % (type(e).__name__, e)}, ensure_ascii=False))
        return 0

    done = set(str(x) for x in (load_json(DONE_FILE, {}).get('done') or []))

    async def fetch_all():
        cred = m.get_cred()
        out = []
        errors = []
        for uid in uids:
            try:
                data = await S.fetch_session_msgs(talker_id=uid, credential=cred)
            except Exception as e:
                errors.append('%s: %s' % (uid, type(e).__name__))
                continue
            msgs = (data or {}).get('messages') or []
            for msg in msgs:
                # 只认对方发来的（自己发的 sender_uid 是助手号自己）
                try:
                    sender = int(msg.get('sender_uid') or 0)
                except Exception:
                    sender = 0
                if sender != uid:
                    continue
                key = str(msg.get('msg_key') or ('%s-%s' % (uid, msg.get('timestamp'))))
                if key in done:
                    continue
                txt = text_of(msg)
                if not txt:
                    continue
                out.append({
                    'msg_key': key,
                    'uid': uid,
                    'text': txt[:500],
                    'timestamp': msg.get('timestamp'),
                })
        return out, errors

    try:
        new, errors = asyncio.run(fetch_all())
    except Exception as e:
        print(json.dumps({'ok': False, 'error': 'fetch: %s: %s' % (type(e).__name__, e)}, ensure_ascii=False))
        return 0

    payload = {'ok': True, 'new': new, 'uids': uids}
    if errors:
        payload['errors'] = errors
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
