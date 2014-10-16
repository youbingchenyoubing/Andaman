#encoding=utf-8
__author__ = 'lxf'
import re
# from os import *
from scrapy import Request, Selector, Item, Field
from scrapy.contrib.spiders import CrawlSpider

class citytempratureItem(Item):
    temprature=Field()

class tempratureSpider(CrawlSpider):
    name = 'tempraturespider1'  # define the spider name
    def start_requests(self):  # send request
        url = 'https://weather.yahoo.com/united-states/new-york/accord-2351708/'
        yield Request(url=url, callback=self.parse)

    def parse(self, response):
        sel = Selector(response)
        xml_current_temprature = sel.xpath('//item/*[name()="yweather:condition"]/@*').extract()  # maybe a bug
        xml_future_temprature = sel.xpath('//item/*[name()="yweather:condition"]/@*').extract()
        a=xml_current_temprature
        return