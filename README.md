# FeedPush

RSS更新推送消息到企业微信/钉钉/蓝信群机器人


## 快速开始

``` bash
curl https://raw.githubusercontent.com/p7e4/FeedPush/master/feedpush.py -O
pip install feedparser aiohttp[speedups] tomli
python3 feedpush.py -c demo.toml
```
后台运行: `nohup python3 feedpush.py -c demo.toml > tmp.log 2>&1 &`


## 配置文件

当webhooks/feeds不使用额外的配置项时可以直接用字符串，否则需要使用[内联表](https://toml.io/cn/v1.0.0#%E5%86%85%E8%81%94%E8%A1%A8)样式

``` toml
# 运行时间间隔, 单位: 分钟
interval = 15

[[project]]
# 群机器人webhooks地址，加签指定sign字段
webhooks = [
    "xxxxx",
    {url="xxxx", sign="xxxx"}
]

# rss订阅源, 可配置项: name显示名称, showText显示内容, onlyText仅显示内容(不包括标题链接等), showAuthor使用author字段代替订阅源名称
feeds = [
    "https://www.solidot.org/index.rss",
    {url="https://www.solidot.org/index.rss", showText=true, name="奇客Solidot"}
]
```

## 截图

![](https://s1.ax1x.com/2023/03/22/ppd4oSx.png)


## FAQ

### 如何防止第一次运行发送大量消息

使用`-s`选项，这会这会忽略第一轮的消息，但是不影响之后的消息推送


### 为什么显示配置文件解析错误

多半是少了结尾逗号, 否则建议对照[toml](https://toml.io/cn/)格式检查一遍


### 更改了配置文件是实时生效吗?

不是，需要手动重新启动



