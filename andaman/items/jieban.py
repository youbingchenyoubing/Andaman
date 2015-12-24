# coding=utf-8
import scrapy


class JiebanItem(scrapy.Item):
    #标题
    title = scrapy.Field()

    #出发时间
    start_time = scrapy.Field()

    #天数
    days = scrapy.Field()

    #出发地
    destination = scrapy.Field()

    #目的地
    departure = scrapy.Field()

    #预订人数
    people= scrapy.Field()

    #文章描述
    description = scrapy.Field()

    #作者头像URL
    author_avatar = scrapy.Field()

    #评论
    comments = scrapy.Field()

    #文章id
    tid = scrapy.Field()

    #旅行方式
    type = scrapy.Field()

    #文章作者
    author = scrapy.Field()
