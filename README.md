### 闲话
QQ 空间爬虫，基于 selenium 模拟登录空间，拿到 cookies，然后使用 requests 抓取好友留言板的所有留言与回复，并生成词图。只抓了留言，本来还想抓说说，不过因为我已经好多年不玩 QQ 空间，感觉它对我已经没什么意义了，遂作罢。

### 使用

#### 获取源码
```shell
$ git clone https://github.com/luolongfei/qzone_spider.git qzone_spider/
$ cd qzone_spider/
```

#### 安装依赖包
```shell
$ pip install -r requirements.txt
```

#### 配置
```shell
# 复制配置
$ cp .env.example .env

# 根据 .env 文件中的注释，将其中对应的项目改为你自己的
$ vim .env
```

#### 抓取
```shell
$ python qzone_spider.py
```

注意：`chromedriver` 路径需要根据你本地浏览器的实际情况填写，这个玩意儿必须和你浏览器版本相对应，否则启动不了。你可以去 [https://chromedriver.chromium.org/downloads](https://chromedriver.chromium.org/downloads) 下载对应的 `chromedriver` 版本，并在 `.env` 文件中指明 `chromedriver 执行文件`的路径。

### 参考
- [https://github.com/ybsdegit/captcha_qq](https://github.com/ybsdegit/captcha_qq)（破解腾讯滑动验证码）
- [https://kylingit.com/blog/qq-%E7%A9%BA%E9%97%B4%E7%88%AC%E8%99%AB%E4%B9%8B%E7%88%AC%E5%8F%96%E7%95%99%E8%A8%80/](https://kylingit.com/blog/qq-%E7%A9%BA%E9%97%B4%E7%88%AC%E8%99%AB%E4%B9%8B%E7%88%AC%E5%8F%96%E7%95%99%E8%A8%80/)
- [https://kylingit.com/blog/qq-%E7%A9%BA%E9%97%B4%E7%88%AC%E8%99%AB%E4%B9%8B%E6%A8%A1%E6%8B%9F%E7%99%BB%E5%BD%95/](https://kylingit.com/blog/qq-%E7%A9%BA%E9%97%B4%E7%88%AC%E8%99%AB%E4%B9%8B%E6%A8%A1%E6%8B%9F%E7%99%BB%E5%BD%95/)

### 开源协议
[MIT](https://opensource.org/licenses/mit-license.php)
