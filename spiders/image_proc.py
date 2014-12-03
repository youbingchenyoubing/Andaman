# coding=utf-8
import hashlib
import json
import os
import random
import re
import time

import qiniu.conf
import qiniu.rs
import qiniu.io
from scrapy import Request, Item, Field, log

import conf
from spiders import AizouCrawlSpider, AizouPipeline


__author__ = 'zephyre'


class ImageProcItem(Item):
    # define the fields for your item here like:
    image = Field()


class AlbumProcItem(Item):
    data = Field()


class AlbumProcSpider(AizouCrawlSpider):
    """
    将images里面的内容，转换成album
    调用参数：--col geo:Locality
    """
    name = 'album-proc'
    uuid = '858c163d-8ea0-4a1e-b425-283f7b7f79a5'

    def start_requests(self):
        yield Request(url='http://www.baidu.com')

    def parse(self, response):
        for db_name, col_name in [tmp.split(':') for tmp in self.param['col']]:
            col = self.fetch_db_col(db_name, col_name, 'mongodb-general')
            for entry in col.find({}, {'images': 1}):
                oid = entry['_id']
                for image in entry['images']:
                    item = AlbumProcItem()
                    data = {'item_id': oid, 'image': image}
                    item['data'] = data
                    yield item


class AlbumProcPipeline(AizouPipeline):
    spiders = [AlbumProcSpider.name]
    spiders_uuid = [AlbumProcSpider.uuid]

    def process_item(self, item, spider):
        if not self.is_handler(item, spider):
            return

        col = self.fetch_db_col('imagestore', 'Album', 'mongodb-general')
        image = item['data']['image']
        oid = item['data']['item_id']

        if 'key' not in image:
            match = re.search(r'qiniudn.com/(.+)$', image['url'])
            image['key'] = match.group(1)

        entry = col.find_one({'image.key': image['key']})
        if entry:
            id_set = set(entry['itemIds'])
            id_set.add(oid)
            entry['itemIds'] = list(id_set)
        else:
            entry = {'image': image, 'itemIds': [oid]}

        col.save(entry)


class ImageProcSpider(AizouCrawlSpider):
    """
    将imageList中的内容，上传到七牛，然后更新images列表
    """
    name = 'image-proc'
    uuid = 'ccef9d95-7b40-441c-a6d0-2c7fb293a4ef'

    handle_httpstatus_list = [400, 403, 404]

    def __init__(self, *a, **kw):
        self.ak = None
        self.sk = None
        self.min_width = 100
        self.min_height = 100
        super(ImageProcSpider, self).__init__(*a, **kw)

    def start_requests(self):
        yield Request(url='http://www.baidu.com')

    def check_img(self, fname):
        """
        检查fname是否为有效的图像（是否能打开，是否能加载，内容是否有误）
        :param fname:
        :return:
        """
        from PIL import Image

        try:
            with open(fname, 'rb') as f:
                img = Image.open(f, 'r')
                img.load()
                w, h = img.size
                if w < self.min_width or h < self.min_height:
                    return False
                else:
                    return True
        except IOError:
            return False

    def parse(self, response):
        db = self.param['db'][0] if 'db' in self.param else None
        col_name = self.param['col'][0] if 'col' in self.param else None
        profile = self.param['profile'][0] if 'profile' in self.param else 'mongodb-general'
        query = json.loads(self.param['query'][0]) if 'query' in self.param else {}

        col_im_c = self.fetch_db_col('imagestore', 'ImageCandidates', 'mongodb-general')
        if db and col_name:
            col = self.fetch_db_col(db, col_name, profile)
            cursor = col.find(query, {'_id': 1}, snapshot=True)
            if 'limit' in self.param:
                cursor.limit(int(self.param['limit'][0]))

            for entry in cursor:
                for img in col_im_c.find({'itemIds': entry['_id']}, snapshot=True):
                    item = ImageProcItem()
                    item['image'] = img
                    url = img['url']
                    yield Request(url=url, meta={'item': item}, headers={'Referer': None}, callback=self.parse_img)
        else:
            cursor = col_im_c.find(query, snapshot=True)
            if 'limit' in self.param:
                cursor.limit(int(self.param['limit'][0]))

            self.log('Estiname: %d images to process...' % cursor.count(), log.INFO)
            for img in cursor:
                item = ImageProcItem()
                item['image'] = img
                url = img['url']
                yield Request(url=url, meta={'item': item}, headers={'Referer': None}, callback=self.parse_img)


    def get_upload_token(self, key, bucket='lvxingpai-img-store', overwrite=True):
        """
        获得七牛的上传凭证
        :param key:
        :param bucket:
        :param overwrite: 是否为覆盖模式
        """
        if not self.ak or not self.sk:
            # 获得上传权限
            section = conf.global_conf.get('qiniu', {})
            self.ak = section['ak']
            self.sk = section['sk']
        qiniu.conf.ACCESS_KEY = self.ak
        qiniu.conf.SECRET_KEY = self.sk

        # 配置上传策略。
        scope = '%s:%s' % (bucket, key) if overwrite else bucket
        policy = qiniu.rs.PutPolicy(scope)
        return policy.token()

    def parse_img(self, response):
        if response.status not in [400, 403, 404]:
            self.log('DOWNLOADED: %s' % response.url, log.INFO)
            meta = response.meta

            fname = './tmp/%d' % (long(time.time() * 1000) + random.randint(1, 10000))
            with open(fname, 'wb') as f:
                f.write(response.body)

            if not self.check_img(fname):
                os.remove(fname)
                return
            else:
                key = 'assets/images/%s' % meta['item']['image']['url_hash']
                sc = False
                self.log('START UPLOADING: %s <= %s' % (key, response.url), log.INFO)

                uptoken = self.get_upload_token(key)
                # 上传的额外选项
                extra = qiniu.io.PutExtra()
                # 文件自动校验crc
                extra.check_crc = 1

                for idx in xrange(5):
                    ret, err = qiniu.io.put_file(uptoken, key, fname, extra)
                    if err:
                        self.log('UPLOADING FAILED #%d: %s, reason: %s, file=%s' % (idx, key, err, fname), log.INFO)
                        continue
                    else:
                        sc = True
                        break
                if not sc:
                    raise IOError
                self.log('UPLOADING COMPLETED: %s' % key, log.INFO)

                # 删除上传成功的文件
                os.remove(fname)

                # 统计信息
                bucket = 'lvxingpai-img-store'
                url = 'http://%s.qiniudn.com/%s?stat' % (bucket, key)
                yield Request(url=url, meta={'item': meta['item'], 'key': key, 'bucket': bucket},
                              callback=self.parse_stat)

    def parse_stat(self, response):
        stat = json.loads(response.body)
        meta = response.meta
        item = meta['item']
        key = meta['key']
        bucket = meta['bucket']

        url = 'http://%s.qiniudn.com/%s?imageInfo' % (bucket, key)
        yield Request(url=url, callback=self.parse_image_info,
                      meta={'item': item, 'key': key, 'bucket': bucket, 'stat': stat})

    def parse_image_info(self, response):
        image_info = json.loads(response.body)
        if 'error' not in image_info:
            meta = response.meta
            item = meta['item']
            key = meta['key']
            stat = meta['stat']

            img = item['image']
            entry = {'url_hash': hashlib.md5(img['url']).hexdigest(),
                     'cTime': long(time.time() * 1000),
                     'cm': image_info['colorModel'],
                     'h': image_info['height'],
                     'w': image_info['width'],
                     'fmt': image_info['format'],
                     'size': stat['fsize'],
                     'url': img['url'],
                     'key': key,
                     'type': stat['mimeType'],
                     'hash': stat['hash']}
            for k, v in entry.items():
                img[k] = v
            if '_id' in img:
                img.pop('_id')

            yield item


class ImageProcPipeline(AizouPipeline):
    spiders = [ImageProcSpider.name]
    spiders_uuid = [ImageProcSpider.uuid]

    def __init__(self, param):
        super(ImageProcPipeline, self).__init__(param)

    def process_item(self, item, spider):
        if not self.is_handler(item, spider):
            return item

        img = item['image']

        col_im = self.fetch_db_col('imagestore', 'Images', 'mongodb-general')
        col_im_c = self.fetch_db_col('imagestore', 'ImageCandidates', 'mongodb-general')
        if 'itemIds' in img:
            item_ids = img.pop('itemIds')
        else:
            item_ids = None
        ops = {'$set': img}
        if item_ids:
            ops['$addToSet'] = {'itemIds': {'$each': item_ids}}

        col_im.update({'key': img['key']}, ops, upsert=True)
        col_im_c.remove({'url_hash': img['url_hash']})

        return item