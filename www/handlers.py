import re, time, json, logging, hashlib, base64, asyncio

from coroweb import get, post
from aiohttp import web
from models import User, Comment, Blog, next_id
from apis import APIError, APIValueError, Page
from config import configs
import markdown2

COOKIE_NAME = 'aweblogsession'
_COOKIE_KEY = configs.session.secret

def user2cookie(user, max_age):
	expires = str(int(time.time() + max_age))
	s = '%s-%s-%s-%s' %(user.id, user.passwd, expires, _COOKIE_KEY)
	L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
	# print('==========%s' %('-'.join(L)))
	return '-'.join(L)

async def cookie2user(cookie_str):
	if not cookie_str:
		return None
	try:
		L = cookie_str.split('-')
		if len(L) != 3:
			return None
		uid, expires, sha1 = L
		if int(expires) < time.time():
			return None
		user = await User.find(uid)
		if user is None:
			return None
		s = '%s-%s-%s-%s' %(uid, user.passwd, expires, _COOKIE_KEY)
		if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
			logging.info('invalid sha1')
			return None
		user.passwd = '*****'
		return user
	except Exception as e:
		logging.exception(e)
		return None
def text2html(text):
	lines = map(lambda s : '<p>%s<p>'  % s.replace('&', '&amp;').replace('<','&lt;').replace('>', '&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))
	return ''.join(lines)

def get_page_index(page_str):
	p = 1
	try:
		p = int(page_str)
	except ValueError as e:
		pass

	if p < 1:
		p = 1
	return p

_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')


@get('/')
async def index(request):
	summary = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
	blogs = [
    	Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
    	Blog(id='2', name='Something New', summary=summary, created_at=time.time()-3600),
    	Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
    ]
	return {
		'__template__':'blogs.html',
		'blogs':blogs
	}

@get('/register')
async def register():
	return {
		'__template__':'register.html'
	}

@get('/signin')
async def signin():
	return {
		'__template__':'signin.html'
	}

@get('/signout')
async def signout(request):
	referer = request.headers.get('Referer')
	r = web.HTTPFound(referer or '/')
	r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
	logging.info('user sign out')
	return r

@get('/manage/blogs/create')
async def manage_blog_create():
	return {
		'__template__':'manage_blog_edit.html',
		'id':'',
		'action':'/api/blogs'
	}

@get('/blog/{id}')
async def get_blog(id):
	blog = await Blog.find(id)
	comments = await Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
	for c in comments:
		c.html_content = text2html(c.content)
	blog.html_content = markdown2.markdown(blog.content)
	return {
		'__template__':'blog.html',
		'blog':blog,
		'comments':comments
	}


@get('/api/users')
async def api_get_users():
	users = await User.findAll(orderBy='created_at desc')
	for u in users:
		u.passwd = '*******'
	return dict(users=users)

@post('/api/user/register')
async def api_redister_user(*, email, name, passwd):
	if not name or not name.strip():
		raise APIValueError('name', 'name is invalid')
	if not email or not _RE_EMAIL.match(email):
		raise APIValueError('email', 'email is invalid')
	if not passwd or not _RE_SHA1.match(passwd):
		raise APIValueError('passwd', 'passwd is invalid')
	users = await User.findAll('email=?', [email])
	if len(users) > 0:
		raise APIError('register:failed', 'email', 'Email has already in use')
	uid = next_id()
	sha1_passwd = '%s:%s' %(uid, passwd)
	user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
	await user.save()
	r = web.Response()
	r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
	user.passwd = '******'
	r.content_type = 'application/json'
	r.body = json.dumps(users, ensure_ascii=False).encode('utf-8')
	return r;

@post('/api/login')
async def api_login(*, email, passwd):
	if not email:
		raise APIValueError('email', 'invalid email')
	if not passwd:
		raise APIValueError('passwd', 'invalid passwd')
	users = await User.findAll('email=?', [email])
	if len(users) == 0:
		raise APIValueError('email', 'Email not exist')
	user = users[0]
	sha1 = hashlib.sha1()
	sha1.update(user.id.encode('utf-8'))
	sha1.update(b':')
	sha1.update(passwd.encode('utf-8'))
	if user.passwd != sha1.hexdigest():
		raise APIValueError('passwd', 'error passwd or email')
	r = web.Response()
	r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
	user.passwd = '*******'
	r.content_type = 'application/json'
	r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
	return r

@post('/api/blogs')
async def api_blog_create(request, *, name, summary, content):
	if not name or not name.strip():
		raise APIValueError('name', 'invalid name')
	if not summary or not summary.strip():
		raise APIValueError('summary', 'invalid summary')
	if not content or not content.strip():
		raise APIValueError('content', 'invalid content')
	blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, name=name.strip(), summary=summary.strip(), content=content.strip())
	await blog.save()
	return blog

@get('/api/blogs/{id}')
async def api_get_blog(*, id):
	blog = await Blog.find(id)
	return blog

@get('/api/blogs')
async def api_blogs(*, page='1'):
	page_index = get_page_index(page)
	num = await Blog.findNumber('count(id)')
	p = Page(num, page_index)
	if num == 0:
		return dict(page=p, blogs=())
	blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
	return dict(page=p, blogs=blogs)
