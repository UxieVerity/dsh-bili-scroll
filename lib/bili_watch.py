#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bili_watch.py —— 私信实时监听守护进程（2026-10-22 主人要求：要比 20 秒轮询更快）

它常驻在 DSH 里，用 bilibili_api 的 Session 收私信事件（内部 6 秒拉一次，
比宿主自己 20 秒一次的轮询快 3 倍多，而且**不再反复启动 python**）。

职责：
  1. 只把 config.json 里 dmReplyUids 名单内的人发来的私聊写进 dm-queue.jsonl；
     名单外的人**连一行都不写**（比"写了再过滤"更安全）。
  2. 每 5 秒写一次心跳文件 dm-watch.heartbeat（宿主靠它判断我还活着）。
  3. 任何异常都不许把宿主带走 —— 出错就打印、继续转。

⚠️ 它只负责"发现"，不负责"回复"：回复仍然由宿主起一个小回合去写。
"""
import asyncio
import json
import os
import sys
import time

_HOME = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HOME)

QUEUE = os.path.join(_HOME, 'dm-queue.jsonl')
HEART = os.path.join(_HOME, 'dm-watch.heartbeat')
CFG = os.path.join(_HOME, 'config.json')
DONE = os.path.join(_HOME, 'dm-done.json')


def log(msg):
    try:
        print('[bili-watch] ' + str(msg), flush=True)
    except Exception:
        pass


def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def whitelist():
    cfg = load_json(CFG, {})
    out = set()
    for x in (cfg.get('dmReplyUids') or []):
        try:
            n = int(str(x).strip())
            if n > 0:
                out.add(n)
        except Exception:
            continue
    return out


def already_done(key):
    done = load_json(DONE, {}).get('done') or []
    return str(key) in set(str(x) for x in done)


def enqueue(item):
    try:
        with open(QUEUE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
        return True
    except Exception as e:
        log('写队列失败：%s' % e)
        return False


def beat(extra=None):
    try:
        with open(HEART, 'w', encoding='utf-8') as f:
            json.dump({'ts': int(time.time()), 'pid': os.getpid(), **(extra or {})}, f, ensure_ascii=False)
    except Exception:
        pass


async def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    import mcp_server as m
    from bilibili_api import session as S

    cred = m.get_cred()
    sess = S.Session(cred)

    @sess.on(S.EventType.TEXT)
    async def on_text(event):
        try:
            # 只认私聊（receiver_type=1）且是"别人发给我"
            if getattr(event, 'receiver_type', 0) != 1:
                return
            sender = int(getattr(event, 'sender_uid', 0) or 0)
            allow = whitelist()
            if sender not in allow:
                return          # ⭐ 名单外的人：连记录都不记录
            key = str(getattr(event, 'msg_key', '') or '')
            if not key or already_done(key):
                return
            text = str(getattr(event, 'content', '') or '').strip()
            if not text:
                return
            if enqueue({'msg_key': key, 'uid': sender, 'text': text[:500], 'ts': int(getattr(event, 'timestamp', 0) or 0)}):
                log('收到名单内私信 uid=%s（已入队）' % sender)
        except Exception as e:
            log('处理事件出错（已吞）：%s' % e)

    beat({'state': 'starting'})
    await sess.run()
    log('已连接，开始监听私信（名单 %s）' % sorted(whitelist()))
    beat({'state': 'running'})

    while True:
        beat({'state': 'running', 'status': sess.get_status()})
        await asyncio.sleep(5)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        log('守护进程挂了：%s' % e)
        traceback.print_exc()
        sys.exit(1)
