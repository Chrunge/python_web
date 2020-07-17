import logging;logging.basicConfig(level = logging.INFO) #导入log记录文件信息

import asyncio, os, json, time
from datetime import datetime

from aiohttp import web


routes = web.RouteTableDef() #采用Flask风格的路由装饰器

@routes.get('/') #将URL与函数关联起来
async def index(request): #一个请求处理器必须是一个协程,且接受一个request实例,返回一个response实例
	# 需要加content_type这个参数，否则会变成下载文件
    return web.Response(body=b'<h1>Awesome</h1>',content_type= 'text/html')

def init():
	# 多看看官方文档，aiohttp和asyncio都要看
	logging.info('Server start at 127.0.0.1:9090')
	app = web.Application() #创建一个Application实例
	app.add_routes(routes) # 注册一个请求处理器,将URL与方法关联起来
	web.run_app(app,host = '127.0.0.1',port = 9090)


init()