#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''ORM就是通过实例对象的语法，完成关系型数据库操作的奇数，是“对象-关系映射”（object/relation mapping）的缩写；
ORM将数据库映射为对象：
1.数据库的表（table）-->>类（class);
2.记录（record，行数据）-->>对象（object）；
3.字段（field）-->>对象的属性（attribute）;
优点：
1.数据模型都在一个地方定义，更容易更新维护和反复利用
2.ORM有现成的工具，很多功能都可以自动完成，比如数据消毒，预处理，事务等等
3.它迫使你使用MVC架构，ORM就是天然的Model，最终使代码更清晰
4.基于ORM的业务代码比较简单且少，语义性好，容易理解
缺点：参见https://www.ruanyifeng.com/blog/2019/02/orm-tutorial.html

使用ORM：
第一步：连接数据库
第二步：把数据库的表，转化为一个类，该类叫做数据模型（Model）；
        模型中可以详细的描述数据库的定义，并定义自己的方法。
第三步：在类中定义方法，以完成数据库的CRUD操作（Create，Read，Update，Delete）
notes：关系：
            1.一对一关系：需要设置2个Model，且每一个实例对应另一个类中的实例
            2.一对多的关系：同上，定义2个Model，一个实例对应另一个类中的多个实例
            3.多对多的关系：需要中间有一张表，记录另外两张表之间的对应关系，即需要定义3个Model
'''
__author__ = 'chrunge qiu'

import asyncio, logging # 支持日志操作
import aiomysql # 为mysql提供了异步IO驱动
import pdb

def log(sql, args=()):
    logging.info('SQL: %s' % sql) # 用于打印出SQL语句

async def create_pool(loop, **kw):
    logging.info('create database connection pool...')
    global __pool 
    __pool = await aiomysql.create_pool( # 创建了一个全局连接池,每个HTTP请求都可以从连接池中获取数据库的数据
        host=kw.get('host', 'localhost'), # 默认定义host为localhost
        port=kw.get('port', 3306), # 默认定义port为3306   
        user=kw['user'], # 用户名通过关键字参数传入
        password=kw['password'], # 密码通过关键字参数传入
        db=kw['database'], # 数据库名字通过关键字参数传入 
        charset=kw.get('charset', 'utf8'), # 默认数据库字符集为utf-8
        autocommit=kw.get('autocommit', True), # 默认自动提交事务
        maxsize=kw.get('maxsize', 10), # 连接池最多接受10个请求
        minsize=kw.get('minsize', 1), # 连接池最少接受1个请求
        loop=loop # 传递消息循环对象loop用于异步执行
    )

# ==============SQL处理函数区==============
# select和execute方法是实现其他Model类中SQL语句都要经常用的方法，原本是全局函数，这里作为静态函数处理
# notes:之所以放在Model类里面作为静态函数处理是为了更好的功能聚合，便于维护，这点与廖老师的处理方法不同，请注意


async def select(sql, args, size=None): # select语句对应选择select方法，传入sql语句和参数
    log(sql, args)
    global __pool

    # 异步等待连接池对象返回可以连接线程，with语句则封装了清理（关闭conn)和处理异常的工作
    async with __pool.get() as conn:
        # 等待连接对象返回DictCursor可以通过dict的方式获取数据库对象，需要通过游标对象执行SQL
        async with conn.cursor(aiomysql.DictCursor) as cur: #async将调用一个协程,并获得子协程的返回结果
            # 所有args都是都通过replace方法把占位符替换为%s
            # args是execute方法的参数
            await cur.execute(sql.replace('?', '%s'), args or ()) #通过替换参数，执行SQL语句
            # pdb.set_trace()   #断点调试
            if size: # 如果指定要返回几行
                rs = await cur.fetchmany(size) # 从数据库中获取指定的行数，fetchmany获取最多指定数量的记录
            else:
                rs = await cur.fetchall() # fetchall获取所有记录
        logging.info('rows returned: %s' % len(rs)) #输出log信息
        return rs #返回结果集

async def execute(sql, args, autocommit=True):
    # execute方法只返回结果数，不返回结果集，用于insert，update这些SQL语句
    log(sql)
    async with __pool.get()  as conn:
        if not autocommit:
            await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # pdb.set_trace()
                await cur.execute(sql.replace('?', '%s'), args) # 执行SQL语句，同时替换占位符
                affected = cur.rowcount # 返回受影响的行数
            if not autocommit:
                await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.rollback() # 事务回滚
            raise e # raise不带参数，则把此处的错误往上抛，为了方便理解还是加e吧  
        return affected



# ========================================Model基类以及其元类=====================
# 对象和关系之间要映射起来，首先考虑创建所有Model类的一个父类，具体的Model对象（就是数据库表在你代码中对应的对象）再继承这个基类


class ModelMetaclass(type):
    # 该元类主要使得Model基类具备以下功能
    # 1.任何继承自Model的类（比如User），会自动通过ModelMetaclass扫描映射关系
    # 并存储到自身的类属性如__table_、__mappings__中
    # 2.创建了一些默认的SQL语句

    def __new__(cls, name, bases, attrs):
        # 排除Model这个基类
        if name=='Model':
            return type.__new__(cls, name, bases, attrs)
        # 获取table名称，一般就是Model类的类名
        tableName = attrs.get('__table__', None) or name #前面的get失败后，就直接赋值name
        logging.info('found model: %s (table: %s)' % (name, tableName))
        # 获取所有的Field和主键名
        mappings = dict()  # 保存属性和值得k,v
        fields = [] # 保存Model类的属性
        primaryKey = None # 保存Model类的主键
        for k, v in attrs.items():
            if isinstance(v, Field): # 如果是Field类，则加入mappings对象
                logging.info('  found mapping: %s ==> %s' % (k, v))
                mappings[k] = v # k,v键值全部保存到mappings中，包括主键和非主键
                if v.primary_key: #如果v是主键即primary_key =True，尝试把其赋值给primaryKey属性
                    if primaryKey: # 如果primaryKey不为空，则说明已有主键，则抛出错误，因为主键只能有一个
                        raise StandardError('Duplicate primary key for field: %s' % k)
                    primaryKey = k # 如果还没有被赋值，则直接赋值
                else: # 如果v不是主键，即primary_key = FALSE的情况
                    fields.append(k) # 非主键全部放到fields列表中

        if not primaryKey: # 如果遍历完还没找到主键，则抛出错误
            raise StandardError('Primary key not found.')

        for k in mappings.keys(): # 清楚mappings，防止实例属性覆盖类的同名属性，造成运行错误
            # attrs中对应的属性则需要删除。作者指的是attrs的属性和mappings的属性发生冲突，具体原因需要自己体会下错误才知道
            attrs.pop(k)

        # %s占位符全部替换为具体的属性名    
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))

        # ==============初始化私有的特别属性============
        attrs['__mappings__'] = mappings # 保存属性和列的映射关系，赋值给mappings
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey # 主键属性名
        attrs['__fields__'] = fields # 除主键外的属性名

        # ==============构造默认的select，insert，update，delete语句======
        # 这里据说不用’，在mysql里面会报错，待验证
        # 默认的select语句貌似没怎么被用到，我感觉通用性如果不好，还不如不加。后面的FindAll方法用到了
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        # insert语句前面有三个占位符，所以从第四个%s开始应该是（用于替换第一个%的值a1，替换第二个%的值a2，替换第三个%的值a3）
        # 默认想执行的应该是update tableName set 属性1=？，属性2=？, .... where 主键 = primary_key
        # a1是tableName没问题，a3应该是主键的属性，a2则通过匿名函数结合map将%s=？全部替换成属性名=？
        # 因此这里的匿名函数就是将%s这个占位符替换成’属性名‘ = ？
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)


def create_args_string(num):    # 在ModelMetaclass的特殊变量中用到

    #insert插入属性是，增加num个数量的占位符
    L = []
    for n in range(num):
        L.append('?')
    return ', '.join(L) # 返回?,?,?,......


class Model(dict, metaclass=ModelMetaclass):
    # 继承dict是为了使用方便，例如对象user['id']即可以轻松通过UserModel去数据库获取到id
    # 元类自然是为了封装我们之前写的具体的SQL处理函数，从数据库获取数据

    def __init__(self, **kw):
        # 调用dict的父类__init__方法用于创建Model,super(类名，类对象)
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        # 调用不存在的属性时返回一些内容
        try:
            return self[key] # 如果存在则正常返回
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        # 设定Model里面的key-value对象，这里value允许为None
        self[key] = value

    def getValue(self, key):
        # 获取某个具体的值，肯定存在的情况下使用该函数，否则会使用__getattr()__
        # 获取实例的key，None是默认值，getattr方法使用参考https://kaimingwan.com/post/language/python/pythonzhong-de-nei-zhi-han-shu-getattr-yu-fan-she
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        # 这个方法当value是None的时候能够返回默认值
        value = getattr(self, key, None)
        if value is None: # 不存在这样的值则直接返回
            # self.__mapping__在metaclass中，用于保存不同实例属性在Model基类中的映射关系
            field = self.__mappings__[key]
            if field.default is not None: # 如果实例的域存在默认值，则使用默认值
                # field.default是callable的话，则直接调用
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value


    # -----------------每个Model类的子类实例应该具备执行SQL的方法比如save-------
    @classmethod # 类方法
    async def findAll(cls, where=None, args=None, **kw):
    # 通过where从句找到对象
        sql = [cls.__select__] # 获取默认的select语句
        if where: # 如果有where语句，则修改SQL变量
            # 这里不用协程，是因为不需要等待数据返回
            sql.append('where') # SQL里面加上where关键字
            sql.append(where) # 这里的where实际上是colName = 'xxx'这样的表达式
        if args is None: # 什么参数？
            args = []

        orderBy = kw.get('orderBy', None) # 从kw中查看是否有orderBy属性
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)

        limit = kw.get('limit', None) # mysql中可以使用limit关键字
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int): # 如果是int类型则增加占位符
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2: # limit可以去2个参数，表示一个范围
                sql.append('?, ?')
                args.extend(limit)
            else: # 其他情况自然是语法问题
                raise ValueError('Invalid limit value: %s' % str(limit))
                # 在原来的默认SQL语句后面再添加语句，要加个空格

        rs = await select(' '.join(sql), args)
        return [cls(**r) for r in rs] # 返回结果，结果是list对象，里面的元素是dict类型的

    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        # 获取行数
        # 这里的_num_是什么意思？别名？我估计是mysql里面一个记录实时查询结果条数的变量
        # find number by select and where. 
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where) # 这里不加空格？
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0: # 结果集为0的情况
            return None
        return rs[0]['_num_'] # 有结果则rs这个list中的第一个词典元素_num_这个key的value值

    @classmethod
    async def find(cls, pk):
        # 根据主键查找
        # pk是dict对象
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    # 这个是实例方法
    async def save(self):
        # args是保存所有Model实例属性和主键的list，使用getValueOrDefault方法的好处是保存默认值
        # 将自己的fields保存进去
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            # 插入失败就是 row !=1
            logging.warn('failed to insert record: affected rows: %s' % rows)


    async def update(self):
        # 这里使用getValue说明只能更新哪些已经存在的值，因此不能使用getValueOrDefault方法
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        # pdb.set_trace()
        rows = await execute(self.__update__, args) # args是属性的list
        if rows != 1:
            logging.warn('failed to update by primary key: affected rows: %s' % rows)

    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warn('failed to remove by primary key: affected rows: %s' % rows)

# ========================类属性================
class Field(object): # 属性的基类，给其他具体的Model类继承

    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default # 如果存在default，在getValueOrDefault中会被用到

    def __str__(self): # 直接print的时候定制输出信息为类名和列类型的列名
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)

class StringField(Field):

    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        # String一般不作为主键，所以默认是FALSE，DDL是数据定义语言，为了配合mysql，所以默认设定为100的长度
        super().__init__(name, ddl, primary_key, default)

class BooleanField(Field):

    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)

class IntegerField(Field):

    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)

class FloatField(Field):

    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)

class TextField(Field):

    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default) # 这个是不能用作主键的对象，所以直接设为FALSE







