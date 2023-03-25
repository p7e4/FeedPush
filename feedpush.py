#!/usr/bin/python3
from string import Template
import feedparser
import argparse
import logging
import asyncio
import aiohttp
import hashlib
import base64
import hmac
import time
import json
import sys
import re
import os

if sys.version_info[1] >= 11:
    import tomllib
else:
    import tomli as tomllib

logging.basicConfig(format="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%m/%d %H:%M:%S", level=logging.INFO)
logger = logging.getLogger(__name__)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36"
}

recordFile = f"{sys.path[0]}/.feedpush"

TagRegx = re.compile(r"<.+?>")

async def worker(session, feeds, messages, history):
    while feeds:
        item = feeds.pop(0)
        try:
            async with session.get(item["url"], ssl=False) as resp:
                feed = feedparser.parse(await resp.text())
        except Exception as e:
            logger.error(e)
            continue
        for entry in feed["entries"]:
            if entry["link"] not in history.get(item["url"], []):
                messages.append({
                    "feedName": item.get("name") or (entry["author"] if item.get("showAuthor") and entry.get("author") else feed["feed"]["title"]),
                    "title": entry["title"].strip(),
                    "link": entry["link"],
                    "showText": f"{TagRegx.sub('', entry['summary']).strip()}\n" if item.get("showText") or item.get("onlyText") else "",
                    "onlyText": item.get("onlyText")
                })
            else:
                break
        if feed["entries"]: history[item["url"]] = [i["link"] for i in feed["entries"]]

async def main(conf, silent):
    if os.path.exists(recordFile):
        with open(recordFile) as f:
            history = json.load(f)
    else:
        history = dict()

    projects = list()
    for item in conf["project"]:
        webhooks = [{"url": i} if isinstance(i, str) else i for i in item["webhooks"]]
        feeds = [{"url": i} if isinstance(i, str) else i for i in item["feeds"]]
        projects.append({"webhooks": webhooks, "feeds": feeds})

    nextRun = int(time.time())
    async with aiohttp.ClientSession(headers=headers) as session:
        while True:
            for item in projects:
                messages = list()
                feeds = item["feeds"][:]
                webhooks = item["webhooks"][:]
                await asyncio.gather(*[worker(session, feeds, messages, history) for i in range(5)])
                if not silent:
                    await asyncio.gather(*[sendMessage(session, webhooks, messages) for i in range(5)])

            with open(recordFile, "w") as f:
                json.dump(history, f)

            if silent: silent=False
            logger.debug("本轮完成")
            if conf.get("interval", 30) < 0: break
            nextRun += conf.get("interval", 15) * 60
            if (sleep:=nextRun - int(time.time())) > 0:
                await asyncio.sleep(sleep)

async def sendMessage(session, webhooks, messages):
    # 企业微信 https://developer.work.weixin.qq.com/document/path/91770
    # 钉钉 https://open.dingtalk.com/document/orgapp/custom-robot-access
    # 飞书 https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN
    # 蓝信 https://openapi.lanxin.cn/doc/#/quick-start/bot-dev/webhook-bot-overview
    MarkDownTemplate = "【$feedName】 [$title]($link)\n\n$showText"
    async def send(code):
        try:
            async with session.post(webhook["url"], params=webhook.get("_sign", {}), json=data) as resp:
                if not resp.headers.get("Content-Type").startswith("application/json") or (await resp.json()).get(code) != 0:
                    logger.error(await resp.text())
        except Exception as e:
            logger.error(e)
    while webhooks:
        webhook = webhooks.pop(0)
        timestamp = int(time.time())
        fq = 0
        if webhook["url"].startswith("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key="):
            # 20/min, 不超过4096个字节
            for msg in messages[::-1]:
                data = {
                   "msgtype": "markdown",
                   "markdown": {
                        "content": msg["showText"].rstrip() if msg["onlyText"] else Template(MarkDownTemplate).substitute(msg)
                    }
                }
                await send("errcode")
                fq += 1
                if fq % 20 == 0 and len(messages) > 20: await asyncio.sleep(60)
        elif webhook["url"].startswith("https://oapi.dingtalk.com/robot/send?access_token="):
            # 20/min
            if webhook.get("sign"):
                sign = hmac.new(webhook["sign"].encode(), f"{timestamp * 1000}\n{webhook['sign']}".encode(), digestmod=hashlib.sha256).digest()
                webhook["_sign"] = {"timestamp": timestamp * 1000, "sign": base64.b64encode(sign).decode()}
            for msg in messages[::-1]:
                data = {
                   "msgtype": "markdown",
                   "markdown": {
                        "title": msg["title"],
                        "text": msg["showText"].rstrip() if msg["onlyText"] else Template(MarkDownTemplate).substitute(msg)
                    }
                }
                await send("errcode")
                fq += 1
                if fq % 20 == 0 and len(messages) > 20: await asyncio.sleep(60)
        elif webhook["url"].find("/v1/bot/hook/messages/create?hook_token") > 0:
            if webhook.get("sign"): 
                webhook["_sign"] = base64.b64encode(hmac.new(f"{timestamp}@{webhook['sign']}".encode(), digestmod=hashlib.sha256).digest()).decode()
            for msg in messages[::-1]:
                data = {
                    "sign": webhook.get("_sign"),
                    "timestamp": str(timestamp),
                    "msgType": "text",
                    "msgData": {
                        "text": {
                            "content": msg["showText"].rstrip() if msg["onlyText"] else f"【{msg['feedName']}】 {msg['title']}\n{msg['showText']}{msg['link']}"
                        }
                    }
                }
                await send("errCode")
        else:
            logger.error(f"未知的webhook类型: {webhook['url']}")

def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", dest="conf", help="conf file", required=True)
    parser.add_argument("-v", "--verbose", help="show verbose", action="store_true")
    parser.add_argument("-s", "--silent", help="don't send messages at the first round", action="store_true")
    args = parser.parse_args()
    if args.conf and os.path.exists(args.conf):
        with open(args.conf, "rb") as f:
            try:
                conf = tomllib.load(f)
            except tomllib.TOMLDecodeError:
                return logger.error("配置文件解析错误")
    else:
        return logger.error(f"配置文件`{args.conf}`不存在")

    if args.verbose: logger.setLevel(logging.DEBUG)
    asyncio.run(main(conf, silent=args.silent))

if __name__ == "__main__":
    cli()

