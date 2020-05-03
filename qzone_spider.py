#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
QQ 空间爬虫

@author mybsdc <mybsdc@gmail.com>
@date 2020/4/10
@time 15:06
"""

import os
import time
import random
import json
import re
import sys
import traceback
from io import BytesIO
from urllib.request import urlretrieve
import requests
import pickle
from PIL import Image
import cv2
import numpy as np
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import jieba
import jieba.analyse
import logging
from wordcloud import WordCloud
from dotenv import load_dotenv


def catch_exception(origin_func):
    def wrapper(self, *args, **kwargs):
        """
        用于异常捕获的装饰器
        :param origin_func:
        :return:
        """
        try:
            return origin_func(self, *args, **kwargs)
        except AssertionError as ae:
            print('参数错误：{}'.format(str(ae)))
        except NoSuchElementException as nse:
            print('匹配元素超时，超过{}秒依然没有发现元素：{}'.format(QzoneSpider.timeout, str(nse)))
        except TimeoutException:
            print(f'请求超时：{self.driver.current_url}')
        except UserWarning as uw:
            print('警告：{}'.format(str(uw)))
        except WebDriverException:
            print('未知错误，可能是 chromedriver 与本地谷歌无头浏览器版本不匹配，可检查并前往 https://chromedriver.chromium.org/downloads '
                  '下载匹配的版本，当然也可能不是这个原因:)')
        except Exception as e:
            print('出错：{} 位置：{}'.format(str(e), traceback.format_exc()))
        finally:
            self.driver.quit()

    return wrapper


class QzoneSpider(object):
    # 超时秒数，包括隐式等待和显式等待
    timeout = 33

    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.129 Safari/537.36'

    # 空间留言板地址
    qzone_message_board_url = 'https://user.qzone.qq.com/proxy/domain/m.qzone.qq.com/cgi-bin/new/get_msgb'

    # 匹配无效内容的正则
    invalid_val_regex = re.compile(r'&.*?;|<.*?>|\n|\[\w+\].*?\[/\w+\]')

    # 匹配汉字和英文
    real_val_regex = re.compile(r'^[\u4e00-\u9fa5]+|[A-Za-z]{3,}$')

    def __init__(self):
        # 加载环境变量
        load_dotenv(verbose=True, override=True, encoding='utf-8')

        self.options = webdriver.ChromeOptions()

        self.options.add_argument(f'user-agent={QzoneSpider.user_agent}')
        self.options.add_experimental_option('excludeSwitches', ['enable-automation'])
        self.options.add_experimental_option('useAutomationExtension', False)
        self.options.add_argument('--disable-extensions')  # 禁用扩展
        self.options.add_argument('--profile-directory=Default')
        self.options.add_argument('--incognito')  # 隐身模式
        self.options.add_argument('--disable-plugins-discovery')
        self.options.add_argument('--start-maximized')
        # self.options.add_argument('--window-size=1366,768')

        self.options.add_argument('--headless')
        self.options.add_argument('--disable-gpu')  # 谷歌官方文档说加上此参数可减少 bug，仅适用于 Windows 系统

        # 解决 unknown error: DevToolsActivePort file doesn't exist
        self.options.add_argument('--no-sandbox')  # 绕过操作系统沙箱环境
        self.options.add_argument('--disable-dev-shm-usage')  # 解决资源限制，仅适用于 Linux 系统

        self.driver = webdriver.Chrome(executable_path=os.getenv('EXECUTABLE_PATH'), options=self.options)
        self.driver.implicitly_wait(QzoneSpider.timeout)

        # 防止通过 window.navigator.webdriver === true 检测模拟浏览器
        # 参考：
        # https://www.selenium.dev/selenium/docs/api/py/webdriver_chrome/selenium.webdriver.chrome.webdriver.html#selenium.webdriver.chrome.webdriver.WebDriver.execute_cdp_cmd
        # https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-addScriptToEvaluateOnNewDocument
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })

        # 统配显式等待
        self.wait = WebDriverWait(self.driver, timeout=QzoneSpider.timeout, poll_frequency=0.5)

        self.cookies_file = 'cookies_jar'
        self.username = os.getenv('YOUR_QQ')
        self.password = os.getenv('PASSWORD')
        self.friend_qq = os.getenv('FRIEND_QQ')

        # QQ空间令牌
        self._g_tk = None

        self.cookies = None

        # 结巴分词配置
        # jieba.enable_paddle()  # paddle 模式可能导致自定义词典不生效，故忽略
        jieba.load_userdict('data/custom_dict.txt')
        jieba.set_dictionary('data/dict.txt.big')
        jieba.setLogLevel(logging.ERROR)
        jieba.analyse.set_stop_words('data/stop_words.txt')
        jieba.analyse.set_idf_path('data/idf.txt.big')

        jieba.suggest_freq('罗龙飞', True)

        # 留言总条数
        self.comment_total = None

    def __login(self, force=False):
        """
        登录 QQ 空间
        获取必要的 cookies 及令牌
        :param force: 是否强制登录，强制登录将忽略已存在的 cookies 文件，走完整登录逻辑
        :return:
        """
        if not force and os.path.exists(self.cookies_file):
            print('发现已存在 cookies 文件，免登录')
            with open(self.cookies_file, 'rb') as f:
                self.cookies = pickle.load(f)
                self._g_tk = self.g_tk(self.cookies)

                return self.cookies, self._g_tk

        self.driver.get('https://qzone.qq.com/')

        login_frame = self.driver.find_element_by_id('login_frame')
        self.driver.switch_to.frame(login_frame)
        self.driver.find_element_by_id('switcher_plogin').click()

        u = self.driver.find_element_by_id('u')
        u.clear()
        u.send_keys(self.username)

        p = self.driver.find_element_by_id('p')
        p.clear()
        p.send_keys(self.password)

        self.driver.find_element_by_id('login_button').click()

        self.__fuck_captcha()

        cookies = {}
        for cookie in self.driver.get_cookies():
            cookies[cookie['name']] = cookie['value']

        # cookies 持久化
        with open(self.cookies_file, 'wb') as f:
            pickle.dump(cookies, f)

        self.cookies = cookies
        self._g_tk = self.g_tk(self.cookies)

        return self.cookies, self._g_tk

    @staticmethod
    def get_track(distance):
        """
        获取移动轨迹
        先加速再减速，滑过一点再反方向滑到正确位置，模拟真人
        :param distance:
        :return:
        """
        # 初速度
        v = 0

        # 单位时间为0.2s来统计轨迹，轨迹即0.2内的位移
        t = 0.2

        # 位移 / 轨迹列表，列表内的一个元素代表0.2s的位移
        tracks = []

        # 当前的位移
        curr_position = 0

        # 到达mid值开始减速
        mid = distance * 7 / 8

        # 先滑过一点，最后再反着滑动回来
        distance += 10

        while curr_position < distance:
            if curr_position < mid:
                # 加速度越小，单位时间的位移越小,模拟的轨迹就越多越详细
                a = random.randint(2, 4)  # 加速运动
            else:
                a = -random.randint(3, 5)  # 减速运动

            # 初速度
            v0 = v

            # 0.2秒时间内的位移
            s = v0 * t + 0.5 * a * (t ** 2)

            # 当前的位置
            curr_position += s

            # 添加到轨迹列表
            tracks.append(round(s))

            # 速度已经达到v,该速度作为下次的初速度
            v = v0 + a * t

        # 反着滑动到大概准确位置
        for i in range(4):
            tracks.append(-random.randint(2, 3))
        for i in range(4):
            tracks.append(-random.randint(1, 3))

        return tracks

    @staticmethod
    def get_distance_x(bg_block, slide_block):
        """
        获取滑块与缺口图块的水平距离
        :param bg_block:
        :param slide_block:
        :return:
        """
        image = cv2.imread(bg_block, 0)  # 带缺口的背景图
        template = cv2.imread(slide_block, 0)  # 缺口图块

        # 图片置灰
        tmp_dir = './images/tmp/'
        os.makedirs(tmp_dir, exist_ok=True)
        image_gray = os.path.join(tmp_dir, 'bg_block_gray.jpg')
        template_gray = os.path.join(tmp_dir, 'slide_block_gray.jpg')
        cv2.imwrite(image_gray, template)
        cv2.imwrite(template_gray, image)
        image = cv2.imread(template_gray)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        image = abs(255 - image)
        cv2.imwrite(template_gray, image)

        # 对比两图重叠区域
        image = cv2.imread(template_gray)
        template = cv2.imread(image_gray)
        result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
        y, x = np.unravel_index(result.argmax(), result.shape)

        return x

    def __fuck_captcha(self, max_retry_num=6):
        """
        模拟真人滑动验证
        :param max_retry_num: 最多尝试 max_retry_num 次
        :return:
        """
        # 切换到验证码 iframe
        self.wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, 'tcaptcha_iframe')))
        time.sleep(0.2)  # 切换 iframe 会有少许延迟，稍作休眠

        for i in range(max_retry_num):
            # 背景图
            bg_block = self.wait.until(EC.visibility_of_element_located((By.ID, 'slideBg')))
            bg_img_width = bg_block.size['width']
            bg_img_x = bg_block.location['x']
            bg_img_url = bg_block.get_attribute('src')

            # 滑块图
            slide_block = self.wait.until(EC.visibility_of_element_located((By.ID, 'slideBlock')))
            slide_block_x = slide_block.location['x']
            slide_img_url = slide_block.get_attribute('src')

            # 小滑块
            drag_thumb = self.wait.until(EC.visibility_of_element_located((By.ID, 'tcaptcha_drag_thumb')))

            # 下载背景图和滑块图
            os.makedirs('./images/', exist_ok=True)
            urlretrieve(bg_img_url, './images/bg_block.jpg')
            urlretrieve(slide_img_url, './images/slide_block.jpg')

            # 获取图片实际宽度的缩放比例
            bg_real_width = Image.open('./images/bg_block.jpg').width
            width_scale = bg_real_width / bg_img_width

            # 获取滑块与缺口的水平方向距离
            distance_x = self.get_distance_x('./images/bg_block.jpg', './images/slide_block.jpg')
            real_distance_x = distance_x / width_scale - (slide_block_x - bg_img_x) + 4

            # 获取移动轨迹
            track_list = self.get_track(real_distance_x)

            # 按住小滑块不放
            ActionChains(self.driver).click_and_hold(on_element=drag_thumb).perform()
            time.sleep(0.2)

            # 分段拖动小滑块
            for track in track_list:
                ActionChains(self.driver).move_by_offset(xoffset=track, yoffset=0).perform()  # 将鼠标移动到当前位置 (x, y)
                time.sleep(0.002)
            time.sleep(1)

            # 放开小滑块
            ActionChains(self.driver).release(on_element=drag_thumb).perform()
            time.sleep(5)  # 跳转需要时间

            # 判断是否通过验证
            if 'user' in self.driver.current_url:
                print('已通过滑动验证')
                self.driver.switch_to.default_content()

                return True
            else:
                print(f'滑块验证不通过，正在进行第{i + 1}次重试...')
                self.wait.until(EC.element_to_be_clickable((By.ID, 'e_reload'))).click()
                time.sleep(0.2)

        raise UserWarning(f'滑块验证不通过，共尝试{max_retry_num}次')

    @staticmethod
    def g_tk(cookies: dict) -> int:
        """
        生成 QQ 空间令牌
        :param cookies:
        :return:
        """
        h = 5381
        s = cookies.get('p_skey', None) or cookies.get('skey', None) or ''
        for c in s:
            h += (h << 5) + ord(c)

        return h & 0x7fffffff

    def __get_comment_list(self, start=0, num=20):
        params = {
            'uin': self.username,
            'hostUin': self.friend_qq,
            'format': 'json',
            'g_tk': self._g_tk,
            'inCharset': 'utf-8',
            'start': start,
            'num': num,
            'outCharset': 'utf-8',
            'qzonetoken': 'e691b89612cd53a0a7d9e17aee2f6850bff21357c8c1194d75e2387f41e9d25a753941030e1f63ad77',
            's': '0.009935855294708196'
        }
        headers = {
            'user-agent': QzoneSpider.user_agent,
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7,und;q=0.6',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty'
        }
        message_board_json = requests.get(QzoneSpider.qzone_message_board_url, params=params, headers=headers,
                                          cookies=self.cookies).text
        msg_data = json.loads(message_board_json)
        code = msg_data['code']

        if code == -4001:
            print('由于之前缓存的 cookies 文件已失效，将尝试自动重新登录...')
            self.__login(force=True)

            return self.__get_comment_list(start, num)
        elif code != 0:
            raise Exception(msg_data['message'])

        if self.comment_total is None:
            self.comment_total = msg_data['data']['total']

        QzoneSpider.row_print(f'已取得第 {start + 1} 到第 {start + num} 条留言')

        return msg_data['data']['commentList']

    @staticmethod
    def parse_comment(comment_list):
        content_list = []
        for comment in comment_list:
            # 无法获取私密留言内容
            if comment['secret'] == 1:
                continue

            content_list.append(comment['htmlContent'])
            for reply in comment['replyList']:
                content_list.append(reply['content'])

        return content_list

    def __get_all_comment(self):
        """
        获取所有留言
        :return:
        """
        all_comment = []
        start = 0
        num = 20  # 每页条数，最多支持 20 条
        while True:
            comment_list = self.__get_comment_list(start=start, num=num)
            if not comment_list:
                break

            all_comment += self.parse_comment(comment_list)
            start += num

            time.sleep(0.02)

        return all_comment

    @staticmethod
    def cut_word(text_list: list):
        """
        割句成词
        :param text_list:
        :return:
        """
        cut_words = []
        for text in text_list:
            real_text = QzoneSpider.invalid_val_regex.sub('', text)
            if not real_text:
                continue

            QzoneSpider.row_print(real_text)

            # 默认精确提取
            # cut_word_list = jieba.lcut(real_text, cut_all=False, use_paddle=False, HMM=True)

            # 基于 TF-IDF 算法的关键词抽取
            cut_word_list = jieba.analyse.extract_tags(real_text, topK=200, withWeight=False, allowPOS=())

            # 过滤无效词
            real_cut_word_list = list(filter(lambda val: QzoneSpider.real_val_regex.match(val), cut_word_list))
            if not real_cut_word_list:
                continue

            cut_words.append(' '.join(real_cut_word_list))

        return ' '.join(cut_words)

    @staticmethod
    def gen_word_cloud_image(text: str, filename: str, mask_file=None) -> None:
        """
        生成词云图
        :param text:
        :param filename:
        :param mask_file:
        :return:
        """
        dirname = os.path.dirname(filename)
        os.makedirs(dirname, exist_ok=True)

        QzoneSpider.row_print('正在生成词云图...')
        mask = np.array(Image.open(mask_file)) if mask_file else None
        scale = 10 if mask else 1  # 当有遮罩时保证图片不失真
        wc = WordCloud(width=1200, height=600, background_color='white', max_words=200, font_path='msyh.ttc',
                       mask=mask, scale=scale)
        wc.generate(text)
        wc.to_file(filename)

    @staticmethod
    def row_print(string):
        """
        在同一行输出字符
        :param string:
        :return:
        """
        print(string, end='\r')  # 回车将回到文本开始处
        sys.stdout.flush()

        time.sleep(0.02)

    @catch_exception
    def run(self):
        self.__login()

        all_comment = self.__get_all_comment()

        comment_cut_word = self.cut_word(all_comment)

        if comment_cut_word:
            word_cloud_comment_img = 'result/word_cloud_{}_{}.png'.format(self.friend_qq, self.comment_total)
            self.gen_word_cloud_image(comment_cut_word, word_cloud_comment_img)
            QzoneSpider.row_print('已生成词云图：{} 共 {} 条留言'.format(word_cloud_comment_img, self.comment_total))

        # 关闭浏览器，释放内存
        self.driver.quit()


if __name__ == '__main__':
    spider = QzoneSpider()
    spider.run()
