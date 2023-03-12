import numpy as np
import os
import re
import datetime
import arxiv
import openai, tenacity
import base64, requests
import argparse
import configparser
import fitz, io, os
from PIL import Image
import gradio
import markdown

class Paper:
    def __init__(self, path, title='', url='', abs='', authers=[], sl=[]):
        # 初始化函数，根据pdf路径初始化Paper对象                
        self.url =  url           # 文章链接
        self.path = path          # pdf路径
        self.sl = sl
        self.section_names = []   # 段落标题
        self.section_texts = {}   # 段落内容    
        if title == '':
            self.pdf = fitz.open(self.path) # pdf文档
            self.title = self.get_title()
            self.parse_pdf()            
        else:
            self.title = title
        self.authers = authers
        self.abs = abs
        self.roman_num = ["I", "II", 'III', "IV", "V", "VI", "VII", "VIII", "IIX", "IX", "X"]
        self.digit_num = [str(d+1) for d in range(10)]
        self.first_image = ''
        
    def parse_pdf(self):
        self.pdf = fitz.open(self.path) # pdf文档
        self.text_list = [page.get_text() for page in self.pdf]
        self.all_text = ' '.join(self.text_list)
        self.section_page_dict = self._get_all_page_index() # 段落与页码的对应字典
        print("section_page_dict", self.section_page_dict)
        self.section_text_dict = self._get_all_page() # 段落与内容的对应字典
        self.section_text_dict.update({"title": self.title})
        self.pdf.close()           
        
    def get_image_path(self, image_path=''):
        """
        将PDF中的第一张图保存到image.png里面，存到本地目录，返回文件名称，供gitee读取
        :param filename: 图片所在路径，"C:\\Users\\Administrator\\Desktop\\nwd.pdf"
        :param image_path: 图片提取后的保存路径
        :return:
        """
        # open file
        max_size = 0
        image_list = []
        with fitz.Document(self.path) as my_pdf_file:
            # 遍历所有页面
            for page_number in range(1, len(my_pdf_file) + 1):
                # 查看独立页面
                page = my_pdf_file[page_number - 1]
                # 查看当前页所有图片
                images = page.get_images()                
                # 遍历当前页面所有图片
                for image_number, image in enumerate(page.get_images(), start=1):           
                    # 访问图片xref
                    xref_value = image[0]
                    # 提取图片信息
                    base_image = my_pdf_file.extract_image(xref_value)
                    # 访问图片
                    image_bytes = base_image["image"]
                    # 获取图片扩展名
                    ext = base_image["ext"]
                    # 加载图片
                    image = Image.open(io.BytesIO(image_bytes))
                    image_size = image.size[0] * image.size[1]
                    if image_size > max_size:
                        max_size = image_size
                    image_list.append(image)
        for image in image_list:                            
            image_size = image.size[0] * image.size[1]
            if image_size == max_size:                
                image_name = f"image.{ext}"
                im_path = os.path.join(image_path, image_name)
                print("im_path:", im_path)
                
                max_pix = 480
                origin_min_pix = min(image.size[0], image.size[1])
                
                if image.size[0] > image.size[1]:
                    min_pix = int(image.size[1] * (max_pix/image.size[0]))
                    newsize = (max_pix, min_pix)
                else:
                    min_pix = int(image.size[0] * (max_pix/image.size[1]))
                    newsize = (min_pix, max_pix)
                image = image.resize(newsize)
                
                image.save(open(im_path, "wb"))
                return im_path, ext
        return None, None
    
    # 定义一个函数，根据字体的大小，识别每个章节名称，并返回一个列表
    def get_chapter_names(self,):
        # # 打开一个pdf文件
        doc = fitz.open(self.path) # pdf文档        
        text_list = [page.get_text() for page in doc]
        all_text = ''
        for text in text_list:
            all_text += text
        # # 创建一个空列表，用于存储章节名称
        chapter_names = []
        for line in all_text.split('\n'):
            line_list = line.split(' ')
            if '.' in line:
                point_split_list = line.split('.')
                space_split_list = line.split(' ')
                if 1 < len(space_split_list) < 5:
                    if 1 < len(point_split_list) < 5 and (point_split_list[0] in self.roman_num or point_split_list[0] in self.digit_num):
                        print("line:", line)
                        chapter_names.append(line)        
        
        return chapter_names
        
    def get_title(self):
        doc = self.pdf # 打开pdf文件
        max_font_size = 0 # 初始化最大字体大小为0
        max_string = "" # 初始化最大字体大小对应的字符串为空
        max_font_sizes = [0]
        for page in doc: # 遍历每一页
            text = page.get_text("dict") # 获取页面上的文本信息
            blocks = text["blocks"] # 获取文本块列表
            for block in blocks: # 遍历每个文本块
                if block["type"] == 0: # 如果是文字类型
                    font_size = block["lines"][0]["spans"][0]["size"] # 获取第一行第一段文字的字体大小            
                    max_font_sizes.append(font_size)
                    if font_size > max_font_size: # 如果字体大小大于当前最大值
                        max_font_size = font_size # 更新最大值
                        max_string = block["lines"][0]["spans"][0]["text"] # 更新最大值对应的字符串
        max_font_sizes.sort()                
        print("max_font_sizes", max_font_sizes[-10:])
        cur_title = ''
        for page in doc: # 遍历每一页
            text = page.get_text("dict") # 获取页面上的文本信息
            blocks = text["blocks"] # 获取文本块列表
            for block in blocks: # 遍历每个文本块
                if block["type"] == 0: # 如果是文字类型
                    cur_string = block["lines"][0]["spans"][0]["text"] # 更新最大值对应的字符串
                    font_flags = block["lines"][0]["spans"][0]["flags"] # 获取第一行第一段文字的字体特征
                    font_size = block["lines"][0]["spans"][0]["size"] # 获取第一行第一段文字的字体大小                         
                    # print(font_size)
                    if abs(font_size - max_font_sizes[-1]) < 0.3 or abs(font_size - max_font_sizes[-2]) < 0.3:                        
                        # print("The string is bold.", max_string, "font_size:", font_size, "font_flags:", font_flags)                            
                        if len(cur_string) > 4 and "arXiv" not in cur_string:                            
                            # print("The string is bold.", max_string, "font_size:", font_size, "font_flags:", font_flags) 
                            if cur_title == ''    :
                                cur_title += cur_string                       
                            else:
                                cur_title += ' ' + cur_string                       
                            # break
        title = cur_title.replace('\n', ' ')                        
        return title

    def _get_all_page_index(self):
        # 定义需要寻找的章节名称列表
        section_list = self.sl
        # 初始化一个字典来存储找到的章节和它们在文档中出现的页码
        section_page_dict = {}
        # 遍历每一页文档
        for page_index, page in enumerate(self.pdf):
            # 获取当前页面的文本内容
            cur_text = page.get_text()
            # 遍历需要寻找的章节名称列表
            for section_name in section_list:
                # 将章节名称转换成大写形式
                section_name_upper = section_name.upper()
                # 如果当前页面包含"Abstract"这个关键词
                if "Abstract" == section_name and section_name in cur_text:
                    # 将"Abstract"和它所在的页码加入字典中
                    section_page_dict[section_name] = page_index
                # 如果当前页面包含章节名称，则将章节名称和它所在的页码加入字典中
                else:
                    if section_name + '\n' in cur_text:
                        section_page_dict[section_name] = page_index
                    elif section_name_upper + '\n' in cur_text:
                        section_page_dict[section_name] = page_index
        # 返回所有找到的章节名称及它们在文档中出现的页码
        return section_page_dict

    def _get_all_page(self):
        """
        获取PDF文件中每个页面的文本信息，并将文本信息按照章节组织成字典返回。
        Returns:
            section_dict (dict): 每个章节的文本信息字典，key为章节名，value为章节文本。
        """
        text = ''
        text_list = []
        section_dict = {}

        # # 先处理Abstract章节
        # for page_index, page in enumerate(self.pdf):
        #     cur_text = page.get_text()
        #     # 如果该页面是Abstract章节所在页面
        #     if page_index == list(self.section_page_dict.values())[0]:
        #         abs_str = "Abstract"
        #         # 获取Abstract章节的起始位置
        #         first_index = cur_text.find(abs_str)
        #         # 查找下一个章节的关键词，这里是Introduction
        #         intro_str = "Introduction"
        #         if intro_str in cur_text:
        #             second_index = cur_text.find(intro_str)
        #         elif intro_str.upper() in cur_text:
        #             second_index = cur_text.find(intro_str.upper())
        #         # 将Abstract章节内容加入字典中
        #         section_dict[abs_str] = cur_text[first_index+len(abs_str)+1:second_index].replace('-\n',
        #                                                                                         '').replace('\n', ' ').split('I.')[0].split("II.")[0]

        # 再处理其他章节：
        text_list = [page.get_text() for page in self.pdf]
        for sec_index, sec_name in enumerate(self.section_page_dict):
            print(sec_index, sec_name, self.section_page_dict[sec_name])
            if sec_index <= 0:
                continue
            else:
                # 直接考虑后面的内容：
                start_page = self.section_page_dict[sec_name]
                if sec_index < len(list(self.section_page_dict.keys()))-1:
                    end_page = self.section_page_dict[list(self.section_page_dict.keys())[sec_index+1]]
                else:
                    end_page = len(text_list)
                print("start_page, end_page:", start_page, end_page)
                cur_sec_text = ''
                if end_page - start_page == 0:
                    if sec_index < len(list(self.section_page_dict.keys()))-1:
                        next_sec = list(self.section_page_dict.keys())[sec_index+1]
                        if text_list[start_page].find(sec_name) == -1:
                            start_i = text_list[start_page].find(sec_name.upper())
                        else:
                            start_i = text_list[start_page].find(sec_name)
                        if text_list[start_page].find(next_sec) == -1:
                            end_i = text_list[start_page].find(next_sec.upper())
                        else:
                            end_i = text_list[start_page].find(next_sec)                        
                        cur_sec_text += text_list[start_page][start_i:end_i]
                else:
                    for page_i in range(start_page, end_page):                    
#                         print("page_i:", page_i)
                        if page_i == start_page:
                            if text_list[start_page].find(sec_name) == -1:
                                start_i = text_list[start_page].find(sec_name.upper())
                            else:
                                start_i = text_list[start_page].find(sec_name)
                            cur_sec_text += text_list[page_i][start_i:]
                        elif page_i < end_page:
                            cur_sec_text += text_list[page_i]
                        elif page_i == end_page:
                            if sec_index < len(list(self.section_page_dict.keys()))-1:
                                next_sec = list(self.section_page_dict.keys())[sec_index+1]
                                if text_list[start_page].find(next_sec) == -1:
                                    end_i = text_list[start_page].find(next_sec.upper())
                                else:
                                    end_i = text_list[start_page].find(next_sec)  
                                cur_sec_text += text_list[page_i][:end_i]
                section_dict[sec_name] = cur_sec_text.replace('-\n', '').replace('\n', ' ')
        return section_dict

# 定义Reader类
class Reader:
    # 初始化方法，设置属性
    def __init__(self, key_word='', query='', filter_keys='', 
                 root_path='./',
                 gitee_key='',
                 sort=arxiv.SortCriterion.SubmittedDate, user_name='defualt', language='cn', key=''):
        self.key = str(key) # OpenAI key
        self.user_name = user_name # 读者姓名
        self.key_word = key_word # 读者感兴趣的关键词
        self.query = query # 读者输入的搜索查询
        self.sort = sort # 读者选择的排序方式
        self.language = language # 读者选择的语言        
        self.filter_keys = filter_keys # 用于在摘要中筛选的关键词
        self.root_path = root_path
        self.file_format = 'md' # or 'txt'，如果为图片，则必须为'md'
        self.save_image = False
        if self.save_image:
            self.gitee_key = self.config.get('Gitee', 'api')
        else:
            self.gitee_key = ''
                
    def get_arxiv(self, max_results=30):
        search = arxiv.Search(query=self.query,
                              max_results=max_results,                              
                              sort_by=self.sort,
                              sort_order=arxiv.SortOrder.Descending,
                              )       
        return search
     
    def filter_arxiv(self, max_results=30):
        search = self.get_arxiv(max_results=max_results)
        print("all search:")
        for index, result in enumerate(search.results()):
            print(index, result.title, result.updated)
            
        filter_results = []   
        filter_keys = self.filter_keys
        
        print("filter_keys:", self.filter_keys)
        # 确保每个关键词都能在摘要中找到，才算是目标论文
        for index, result in enumerate(search.results()):
            abs_text = result.summary.replace('-\n', '-').replace('\n', ' ')
            meet_num = 0
            for f_key in filter_keys.split(" "):
                if f_key.lower() in abs_text.lower():
                    meet_num += 1
            if meet_num == len(filter_keys.split(" ")):
                filter_results.append(result)
                # break
        print("filter_results:", len(filter_results))
        print("filter_papers:")
        for index, result in enumerate(filter_results):
            print(index, result.title, result.updated)
        return filter_results
    
    def validateTitle(self, title):
        # 将论文的乱七八糟的路径格式修正
        rstr = r"[\/\\\:\*\?\"\<\>\|]" # '/ \ : * ? " < > |'
        new_title = re.sub(rstr, "_", title) # 替换为下划线
        return new_title

    def download_pdf(self, filter_results):
        # 先创建文件夹
        date_str = str(datetime.datetime.now())[:13].replace(' ', '-')        
        key_word = str(self.key_word.replace(':', ' '))        
        path = self.root_path  + 'pdf_files/' + self.query.replace('au: ', '').replace('title: ', '').replace('ti: ', '').replace(':', ' ')[:25] + '-' + date_str
        try:
            os.makedirs(path)
        except:
            pass
        print("All_paper:", len(filter_results))
        # 开始下载：
        paper_list = []
        for r_index, result in enumerate(filter_results):
            try:
                title_str = self.validateTitle(result.title)
                pdf_name = title_str+'.pdf'
                # result.download_pdf(path, filename=pdf_name)
                self.try_download_pdf(result, path, pdf_name)
                paper_path = os.path.join(path, pdf_name)
                print("paper_path:", paper_path)
                paper = Paper(path=paper_path,
                              url=result.entry_id,
                              title=result.title,
                              abs=result.summary.replace('-\n', '-').replace('\n', ' '),
                              authers=[str(aut) for aut in result.authors],
                              )
                # 下载完毕，开始解析：
                paper.parse_pdf()
                paper_list.append(paper)
            except Exception as e:
                print("download_error:", e)
                pass
        return paper_list
    
    @tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
                    stop=tenacity.stop_after_attempt(5),
                    reraise=True)
    def try_download_pdf(self, result, path, pdf_name):
        result.download_pdf(path, filename=pdf_name)
    
    @tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
                    stop=tenacity.stop_after_attempt(5),
                    reraise=True)
    def upload_gitee(self, image_path, image_name='', ext='png'):
        """
        上传到码云
        :return:
        """ 
        with open(image_path, 'rb') as f:
            base64_data = base64.b64encode(f.read())
            base64_content = base64_data.decode()
        
        date_str = str(datetime.datetime.now())[:19].replace(':', '-').replace(' ', '-') + '.' + ext
        path = image_name+ '-' +date_str
        
        payload = {
            "access_token": self.gitee_key,
            "owner": self.config.get('Gitee', 'owner'),
            "repo": self.config.get('Gitee', 'repo'),
            "path": self.config.get('Gitee', 'path'),
            "content": base64_content,
            "message": "upload image"
        }
        # 这里需要修改成你的gitee的账户和仓库名，以及文件夹的名字：
        url = f'https://gitee.com/api/v5/repos/'+self.config.get('Gitee', 'owner')+'/'+self.config.get('Gitee', 'repo')+'/contents/'+self.config.get('Gitee', 'path')+'/'+path
        rep = requests.post(url, json=payload).json()
        print("rep:", rep)
        if 'content' in rep.keys():
            image_url = rep['content']['download_url']
        else:
            image_url = r"https://gitee.com/api/v5/repos/"+self.config.get('Gitee', 'owner')+'/'+self.config.get('Gitee', 'repo')+'/contents/'+self.config.get('Gitee', 'path')+'/' + path
            
        return image_url
    
    def summary_with_chat(self, paper_list, key):
        htmls = []
        for paper_index, paper in enumerate(paper_list):
            # 第一步先用title，abs，和introduction进行总结。
            text = ''
            text += 'Title:' + paper.title
            text += 'Url:' + paper.url
            text += 'Abstrat:' + paper.abs
            # intro
            text += list(paper.section_text_dict.values())[0]
            max_token = 2500 * 4
            text = text[:max_token]
            chat_summary_text = self.chat_summary(text=text, key=str(key))           
            htmls.append(chat_summary_text)
            
            # TODO 往md文档中插入论文里的像素最大的一张图片，这个方案可以弄的更加智能一些：
            first_image, ext = paper.get_image_path()
            if first_image is None or self.gitee_key == '':
                pass
            else:                
                image_title = self.validateTitle(paper.title)
                image_url = self.upload_gitee(image_path=first_image, image_name=image_title, ext=ext)
                htmls.append("\n")
                htmls.append("![Fig]("+image_url+")")
                htmls.append("\n")
            # 第二步总结方法：
            # TODO，由于有些文章的方法章节名是算法名，所以简单的通过关键词来筛选，很难获取，后面需要用其他的方案去优化。
            method_key = ''
            for parse_key in paper.section_text_dict.keys():
                if 'method' in parse_key.lower() or 'approach' in parse_key.lower():
                    method_key = parse_key
                    break
                
            if method_key != '':
                text = ''
                method_text = ''
                summary_text = ''
                summary_text += "<summary>" + chat_summary_text
                # methods                
                method_text += paper.section_text_dict[method_key]   
                # TODO 把这个变成tenacity的自动判别！             
                max_token = 2500 * 4
                text = summary_text + "\n <Methods>:\n" + method_text 
                text = text[:max_token]
                chat_method_text = self.chat_method(text=text, key=str(key))
                htmls.append(chat_method_text)
            else:
                chat_method_text = ''
            htmls.append("\n")
            
            # 第三步总结全文，并打分：
            conclusion_key = ''
            for parse_key in paper.section_text_dict.keys():
                if 'conclu' in parse_key.lower():
                    conclusion_key = parse_key
                    break
            
            text = ''
            conclusion_text = ''
            summary_text = ''
            summary_text += "<summary>" + chat_summary_text + "\n <Method summary>:\n" + chat_method_text            
            if conclusion_key != '':
                # conclusion                
                conclusion_text += paper.section_text_dict[conclusion_key]                
                max_token = 2500 * 4
                text = summary_text + "\n <Conclusion>:\n" + conclusion_text 
            else:
                text = summary_text
            text = text[:max_token]
            chat_conclusion_text = self.chat_conclusion(text=text, key=str(key))
            htmls.append(chat_conclusion_text)
            htmls.append("\n")
            md_text = "\n".join(htmls)
            
            return markdown.markdown(md_text)
            
            
    @tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
                    stop=tenacity.stop_after_attempt(5),
                    reraise=True)
    def chat_conclusion(self, text, key):
        openai.api_key = key
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            # prompt需要用英语替换，少占用token。
            messages=[
                {"role": "system", "content": "你是一个["+self.key_word+"]领域的审稿人，你需要严格评审这篇文章"},  # chatgpt 角色
                {"role": "assistant", "content": "这是一篇英文文献的<summary>和<conclusion>部分内容，其中<summary>你已经总结好了，但是<conclusion>部分，我需要你帮忙归纳下面问题："+text},  # 背景知识，可以参考OpenReview的审稿流程
                {"role": "user", "content": """                 
                 8. 做出如下总结：
                    - (1):这篇工作的意义如何？
                    - (2):从创新点、性能、工作量这三个维度，总结这篇文章的优点和缺点。                   
                    .......
                 按照后面的格式输出: 
                 8. Conclusion:
                    - (1):xxx;                     
                    - (2):创新点: xxx; 性能: xxx; 工作量: xxx;                      
                 
                 务必使用中文回答（专有名词需要用英文标注)，语句尽量简洁且学术，不要和之前的<summary>内容重复，数值使用原文数字, 务必严格按照格式，将对应内容输出到xxx中，.......代表按照实际需求填写，如果没有可以不用写.                 
                 """},
            ]
        )
        result = ''
        for choice in response.choices:
            result += choice.message.content
        print("conclusion_result:\n", result)
        return result            
    
    @tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
                    stop=tenacity.stop_after_attempt(5),
                    reraise=True)
    def chat_method(self, text, key):
        openai.api_key = key
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "你是一个["+self.key_word+"]领域的科研人员，善于使用精炼的语句总结论文"},  # chatgpt 角色
                {"role": "assistant", "content": "这是一篇英文文献的<summary>和<Method>部分内容，其中<summary>你已经总结好了，但是<Methods>部分，我需要你帮忙阅读并归纳下面问题："+text},  # 背景知识
                {"role": "user", "content": """                 
                 7. 详细描述这篇文章的方法思路。比如说它的步骤是：
                    - (1):...
                    - (2):...
                    - (3):...
                    - .......
                 按照后面的格式输出: 
                 7. Methods:
                    - (1):xxx; 
                    - (2):xxx; 
                    - (3):xxx;  
                    .......     
                 
                 务必使用中文回答（专有名词需要用英文标注)，语句尽量简洁且学术，不要和之前的<summary>内容重复，数值使用原文数字, 务必严格按照格式，将对应内容输出到xxx中，按照\n换行，.......代表按照实际需求填写，如果没有可以不用写.                 
                 """},
            ]
        )
        result = ''
        for choice in response.choices:
            result += choice.message.content
        print("method_result:\n", result)
        return result
    
    @tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
                    stop=tenacity.stop_after_attempt(5),
                    reraise=True)
    def chat_summary(self, text, key):
        openai.api_key = key
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "你是一个["+self.key_word+"]领域的科研人员，善于使用精炼的语句总结论文"},  # chatgpt 角色
                {"role": "assistant", "content": "这是一篇英文文献的标题，作者，链接，Abstract和Introduction部分内容，我需要你帮忙阅读并归纳下面问题："+text},  # 背景知识
                {"role": "user", "content": """                 
                 1. 标记出这篇文献的标题(加上中文翻译)
                 2. 列举所有的作者姓名 (使用英文)
                 3. 标记第一作者的单位（只输出中文翻译）                 
                 4. 标记出这篇文章的关键词(使用英文)
                 5. 论文链接，Github代码链接（如果有的话，没有的话请填写Github:None）
                 6. 按照下面四个点进行总结：
                    - (1):这篇文章的研究背景是什么？
                    - (2):过去的方法有哪些？它们存在什么问题？本文和过去的研究有哪些本质的区别？Is the approach well motivated?
                    - (3):本文提出的研究方法是什么？
                    - (4):本文方法在什么任务上，取得了什么性能？性能能否支持他们的目标？
                 按照后面的格式输出:                  
                 1. Title: xxx
                 2. Authors: xxx
                 3. Affiliation: xxx                
                 4. Keywords: xxx   
                 5. Urls: xxx or xxx , xxx      
                 6. Summary:
                    - (1):xxx;
                    - (2):xxx;
                    - (3):xxx; 
                    - (4):xxx.    
                 
                 务必使用中文回答（专有名词需要用英文标注)，语句尽量简洁且学术，不要有太多重复的信息，数值使用原文数字, 务必严格按照格式，将对应内容输出到xxx中，按照\n换行.                 
                 """},
            ]
        )
        result = ''
        for choice in response.choices:
            result += choice.message.content
        print("summary_result:\n", result)
        return result        
            
    def export_to_markdown(self, text, file_name, mode='w'):
        # 使用markdown模块的convert方法，将文本转换为html格式
        # html = markdown.markdown(text)
        # 打开一个文件，以写入模式
        with open(file_name, mode, encoding="utf-8") as f:
            # 将html格式的内容写入文件
            f.write(text)        

    # 定义一个方法，打印出读者信息
    def show_info(self):        
        print(f"Key word: {self.key_word}")
        print(f"Query: {self.query}")
        print(f"Sort: {self.sort}")                

def upload_pdf(key, text, file):
    # 检查两个输入都不为空
    if not key or not text or not file:
        return "两个输入都不能为空，请输入字符并上传 PDF 文件！"
    # 判断PDF文件
    if file and file.name.split(".")[-1].lower() != "pdf":
        return '请勿上传非 PDF 文件！'
    else:
        section_list = text.split(',')
        paper_list = [Paper(path=file, sl=section_list)]
        # 创建一个Reader对象
        reader = Reader()
        sum_info = reader.summary_with_chat(paper_list=paper_list, key=key)
        return sum_info

# 标题
title = "ChatPaper <img src='https://visitor-badge.laobi.icu/badge?page_id=https://huggingface.co/spaces/wangrongsheng/ChatPaper'>"
# 描述
description = '''<div align='left'>

<img align='right' src='https://i.328888.xyz/2023/03/12/vH9dU.png' width="200">

Use ChatGPT to summary the papers.Star our Github [🌟ChatPaper](https://github.com/kaixindelele/ChatPaper) .

💗如果您觉得我们的项目对您有帮助，还请您给我们一些鼓励！💗

🔴请注意：千万不要用于严肃的学术场景，只能用于论文阅读前的初筛！

</div>
'''
# 创建Gradio界面
ip = [
    gradio.inputs.Textbox(label="请输入你的API-key(必填)", default=""),
    gradio.inputs.Textbox(label="请输入论文大标题索引(用英文逗号隔开,必填)", default="'Abstract,Introduction,Related Work,Background,Preliminary,Problem Formulation,Methods,Methodology,Method,Approach,Approaches,Materials and Methods,Experiment Settings,Experiment,Experimental Results,Evaluation,Experiments,Results,Findings,Data Analysis,Discussion,Results and Discussion,Conclusion,References'"),
    gradio.inputs.File(label="请上传论文PDF(必填)")
]

interface = gradio.Interface(fn=upload_pdf, inputs=ip, outputs="html", title=title, description=description)

# 运行Gradio应用程序
interface.launch()